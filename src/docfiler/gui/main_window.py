"""Main window for Document Filer GUI.

This module provides the main application window with file browsing and
batch processing capabilities.
"""

import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QListView,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import load_config
from ..vlm_service import FilingSuggestion, create_vlm_service
from ..cli.context_generator import generate_context
from .file_viewer import FileViewerWidget

logger = logging.getLogger(__name__)


class CheckableListView(QListView):
    """QListView that supports shift-click for mass checkbox toggling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_index = None

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        
        if not index.isValid():
            super().mousePressEvent(event)
            return

        # Check if shift is held and we have a previous index
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and self.last_index is not None:
            model = self.model()
            if model and hasattr(model, "itemFromIndex"):
                target_item = model.itemFromIndex(index)
                
                # Capture state before super()
                old_state = target_item.checkState()
                
                # Let super process (handles selection and potential toggle)
                super().mousePressEvent(event)
                
                # Get state after super()
                new_state = target_item.checkState()
                
                # If clicking the text (no toggle happened), we force a toggle 
                # based on the last item's state or just invert.
                if new_state == old_state:
                    new_state = Qt.CheckState.Unchecked if old_state == Qt.CheckState.Checked else Qt.CheckState.Checked
                    target_item.setCheckState(new_state)

                start_row = min(self.last_index.row(), index.row())
                end_row = max(self.last_index.row(), index.row())
                
                # Apply new state to the whole range
                for row in range(start_row, end_row + 1):
                    item = model.item(row)
                    if item:
                        item.setCheckState(new_state)
                
                self.last_index = index
                return

        super().mousePressEvent(event)
        self.last_index = index


class ProcessingThread(QThread):
    """Background thread for processing documents."""

    progress = pyqtSignal(int, int)  # current, total
    file_processed = pyqtSignal(str, object)  # file_path, suggestion (or exception)
    finished = pyqtSignal()

    def __init__(self, files, vlm_service):
        """Initialize the processing thread.

        Args:
            files: List of file paths to process.
            vlm_service: VLM service instance.
        """
        super().__init__()
        self.files = files
        self.vlm_service = vlm_service

    def run(self):
        """Run the processing in background."""
        total = len(self.files)

        for idx, file_path in enumerate(self.files, 1):
            try:
                suggestion = self.vlm_service.analyze_document(file_path)
                self.file_processed.emit(str(file_path), suggestion)
            except Exception as e:
                self.file_processed.emit(str(file_path), e)

            self.progress.emit(idx, total)

        self.finished.emit()


class ContextGenerationThread(QThread):
    """Background thread for generating filing context."""

    finished = pyqtSignal(object)  # result (str) or exception

    def __init__(self, source_path):
        """Initialize the thread.

        Args:
            source_path: Path to the organized document repository.
        """
        super().__init__()
        self.source_path = source_path

    def run(self):
        """Run the context generation."""
        try:
            # Run with default parameters from CLI
            context = generate_context(
                self.source_path,
                max_depth=8,
                max_files_per_dir=100
            )
            self.finished.emit(context)
        except Exception as e:
            logger.error(f"Error generating context: {e}")
            self.finished.emit(e)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        self.config = None
        self.vlm_service = None
        self.files = []
        self.suggestions = {}  # file_path -> FilingSuggestion
        self.current_file_index = -1
        self.processing_thread = None

        self._init_ui()
        self._load_config()

        # Automatically load default directory if it exists
        default_dir = Path.home() / "GDrive" / "SHARED" / "__IN__"
        if default_dir.exists() and default_dir.is_dir():
            self._load_folder(str(default_dir))

    def _init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Document Filer")
        self.setMinimumSize(1000, 700)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout
        main_layout = QHBoxLayout(central)

        # Left panel - file list
        left_panel = QVBoxLayout()

        # Folder selection
        folder_button = QPushButton("Open Folder...")
        folder_button.clicked.connect(self._open_folder)
        left_panel.addWidget(folder_button)

        # File list with checkboxes
        self.file_list_model = QStandardItemModel()
        self.file_list = CheckableListView()
        self.file_list.setModel(self.file_list_model)
        self.file_list.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.file_list.selectionModel().currentChanged.connect(self._on_file_selected)
        left_panel.addWidget(self.file_list)

        # Right panel - file viewer
        self.file_viewer = FileViewerWidget()
        self.file_viewer.filename_changed.connect(self._on_viewer_filename_changed)
        self.file_viewer.destination_changed.connect(self._on_viewer_destination_changed)
        main_layout.addWidget(self.file_viewer, 2)
        selection_layout = QHBoxLayout()
        select_all_button = QPushButton("Select All")
        select_all_button.clicked.connect(self._select_all_files)
        selection_layout.addWidget(select_all_button)

        select_none_button = QPushButton("Select None")
        select_none_button.clicked.connect(self._select_no_files)
        selection_layout.addWidget(select_none_button)
        left_panel.addLayout(selection_layout)

        # Processing controls
        self.process_button = QPushButton("Process Selected Files")
        self.process_button.clicked.connect(self._process_selected)
        left_panel.addWidget(self.process_button)

        # Context generation
        self.context_button = QPushButton("Generate Filing Context")
        self.context_button.setToolTip("Analyze organized documents to update filing conventions")
        self.context_button.clicked.connect(self._generate_context)
        left_panel.addWidget(self.context_button)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_panel.addWidget(self.progress_bar)

        # Execute buttons - separate rename and move
        execute_layout = QVBoxLayout()

        rename_button = QPushButton("Rename Selected Files (in place)")
        rename_button.clicked.connect(self._execute_rename)
        execute_layout.addWidget(rename_button)

        move_button = QPushButton("Rename and Move Selected Files")
        move_button.clicked.connect(self._execute_move)
        execute_layout.addWidget(move_button)

        left_panel.addLayout(execute_layout)

        main_layout.addLayout(left_panel, 1)

    def _load_config(self):
        """Load application configuration."""
        try:
            self.config = load_config()
            logger.info(f"Configuration loaded: Provider={self.config.vlm_provider}")

            # Create VLM service
            self.vlm_service = create_vlm_service(self.config)
            
            # Update file viewer with source dir
            if self.config.source_dir:
                self.file_viewer.source_dir = self.config.source_dir

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            QMessageBox.critical(
                self,
                "Configuration Error",
                f"Failed to load configuration:\n{e}\n\nPlease check your .env file.",
            )
            sys.exit(1)

    def _open_folder(self):
        """Open folder selection dialog."""
        # Default to ~/GDrive/SHARED/__IN__ directory
        default_dir = str(Path.home() / "GDrive" / "SHARED" / "__IN__")

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder with Documents",
            default_dir,
            QFileDialog.Option.ShowDirsOnly,
        )

        if folder:
            self._load_folder(folder)

    def _load_folder(self, folder_path: str):
        """Load files from a folder.

        Args:
            folder_path: Path to the folder.
        """
        folder = Path(folder_path)
        logger.info(f"Loading folder: {folder}")

        # Find all supported files
        patterns = ["*.pdf", "*.png", "*.jpg", "*.jpeg", "*.tiff", "*.tif", "*.bmp"]
        self.files = []

        for pattern in patterns:
            self.files.extend(folder.glob(pattern))

        logger.info(f"Found {len(self.files)} files")

        # Update file list
        self.file_list_model.clear()
        self.suggestions.clear()
        self.file_list.last_index = None  # Reset shift-click starting point

        for file_path in self.files:
            item = QStandardItem(file_path.name)
            item.setCheckable(True)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(str(file_path), Qt.ItemDataRole.UserRole)  # Store full path
            self.file_list_model.appendRow(item)
            
            # Pre-populate with current filename by default
            self.suggestions[str(file_path)] = FilingSuggestion(
                filename=file_path.name,
                destination="",
                confidence=1.0,
                reasoning="Current state"
            )

        if self.files:
            # Select first item
            first_index = self.file_list_model.index(0, 0)
            self.file_list.setCurrentIndex(first_index)

    def _on_file_selected(self, current, previous):
        """Handle file selection in the list.

        Args:
            current: Current QModelIndex
            previous: Previous QModelIndex
        """
        if not current.isValid():
            return
        
        row = current.row()
        if row < 0 or row >= len(self.files):
            return

        self.current_file_index = row
        file_path = self.files[row]

        # Update viewer
        self.file_viewer.set_file(file_path)

        # If we have a suggestion for this file, display it
        if str(file_path) in self.suggestions:
            suggestion = self.suggestions[str(file_path)]
            if isinstance(suggestion, FilingSuggestion):
                self.file_viewer.set_suggestion(
                    suggestion.filename,
                    suggestion.destination,
                    suggestion.confidence,
                    suggestion.reasoning,
                )
            else:
                # It might be an Exception or None
                self.file_viewer.clear_suggestion()
        else:
            # No suggestion at all for this file
            self.file_viewer.clear_suggestion()

    def _on_viewer_filename_changed(self, text):
        """Handle manual filename changes in the viewer."""
        if self.current_file_index >= 0:
            file_path = str(self.files[self.current_file_index])
            suggestion = self.suggestions.get(file_path)
            if isinstance(suggestion, FilingSuggestion):
                suggestion.filename = text
            else:
                self.suggestions[file_path] = FilingSuggestion(
                    filename=text,
                    destination="",
                    confidence=1.0,
                    reasoning="Manual override"
                )

    def _on_viewer_destination_changed(self, text):
        """Handle manual destination changes in the viewer."""
        if self.current_file_index >= 0:
            file_path = str(self.files[self.current_file_index])
            suggestion = self.suggestions.get(file_path)
            if isinstance(suggestion, FilingSuggestion):
                suggestion.destination = text
            else:
                self.suggestions[file_path] = FilingSuggestion(
                    filename=Path(file_path).name,
                    destination=text,
                    confidence=1.0,
                    reasoning="Manual override"
                )

    def _process_selected(self):
        """Process only the checked files in the list."""
        checked_files = []
        for i in range(self.file_list_model.rowCount()):
            item = self.file_list_model.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                file_path = item.data(Qt.ItemDataRole.UserRole)
                if file_path:
                    checked_files.append(Path(file_path))

        if not checked_files:
            QMessageBox.warning(self, "No Selection", "Please check at least one file to process.")
            return

        # Disable only action buttons during processing
        # The user can still browse and select files
        self.process_button.setEnabled(False)
        self.context_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(checked_files))
        self.progress_bar.setValue(0)

        # Start processing thread
        self.processing_thread = ProcessingThread(checked_files, self.vlm_service)
        self.processing_thread.progress.connect(self._on_progress)
        self.processing_thread.file_processed.connect(self._on_file_processed)
        self.processing_thread.finished.connect(self._on_processing_finished)
        self.processing_thread.start()

    def _on_progress(self, current: int, total: int):
        """Handle progress update.

        Args:
            current: Current file number.
            total: Total number of files.
        """
        self.progress_bar.setValue(current)
        logger.info(f"Progress: {current}/{total}")

    def _on_file_processed(self, file_path: str, result):
        """Handle a file being processed.

        Args:
            file_path: Path to the processed file.
            result: FilingSuggestion or Exception.
        """
        if isinstance(result, Exception):
            logger.error(f"Error processing {file_path}: {result}")
            self.suggestions[file_path] = result  # Store exception to signal failure
            # Mark as error in the list
            for i in range(self.file_list_model.rowCount()):
                item = self.file_list_model.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == file_path:
                    item.setText(f"❌ {Path(file_path).name}")
                    break
        else:
            # Store suggestion
            self.suggestions[file_path] = result

            # Update list item
            for i in range(self.file_list_model.rowCount()):
                item = self.file_list_model.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == file_path:
                    item.setText(f"✓ {Path(file_path).name}")
                    break

            # If this is the currently selected file, update viewer
            if self.current_file_index >= 0:
                current_path = str(self.files[self.current_file_index])
                if current_path == file_path:
                    self.file_viewer.set_suggestion(
                        result.filename,
                        result.destination,
                        result.confidence,
                        result.reasoning,
                    )

    def _on_processing_finished(self):
        """Handle processing completion."""
        self.progress_bar.setVisible(False)
        self.process_button.setEnabled(True)
        self.context_button.setEnabled(True)

        # Log summary instead of a popup
        success_count = sum(1 for s in self.suggestions.values() if isinstance(s, FilingSuggestion))
        error_count = sum(1 for s in self.suggestions.values() if isinstance(s, Exception))
        
        logger.info(f"Processing Complete: {success_count} successful, {error_count} failed")

    def _select_all_files(self):
        """Select all files in the list."""
        for i in range(self.file_list_model.rowCount()):
            item = self.file_list_model.item(i)
            if item:
                item.setCheckState(Qt.CheckState.Checked)
        logger.debug("Selected all files")

    def _select_no_files(self):
        """Deselect all files in the list."""
        for i in range(self.file_list_model.rowCount()):
            item = self.file_list_model.item(i)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)
        logger.debug("Deselected all files")

    def _get_selected_files(self):
        """Get list of selected file paths with suggestions.
        
        Returns:
            List of tuples: (file_path_str, suggestion)
        """
        selected = []
        for i in range(self.file_list_model.rowCount()):
            item = self.file_list_model.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                file_path_str = item.data(Qt.ItemDataRole.UserRole)
                if file_path_str in self.suggestions:
                    suggestion = self.suggestions[file_path_str]
                    if isinstance(suggestion, FilingSuggestion):
                        selected.append((file_path_str, suggestion))
        return selected

    def _execute_rename(self):
        """Rename selected files in place (same directory)."""
        selected = self._get_selected_files()

        if not selected:
            QMessageBox.warning(
                self,
                "No Files Selected",
                "Please select files and process them first.",
            )
            return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Confirm Rename",
            f"This will rename {len(selected)} file(s) in their current location.\n"
            "This operation cannot be undone.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Execute rename operations
        success_count = 0
        error_count = 0

        # Prepare state migration for successful renames
        migrated_suggestions = {}
        
        for file_path_str, suggestion in selected:
            file_path = Path(file_path_str)
            new_path = file_path.parent / suggestion.filename

            try:
                if new_path.exists() and new_path != file_path:
                    logger.warning(f"Target file already exists: {new_path}")
                    error_count += 1
                    continue

                file_path.rename(new_path)
                logger.info(f"Renamed {file_path_str} -> {new_path}")
                
                # Keep the suggestion but update it for the new path
                # Also mark as successfully renamed for state migration
                migrated_suggestions[str(new_path)] = suggestion
                success_count += 1

            except Exception as e:
                logger.error(f"Failed to rename {file_path}: {e}", exc_info=True)
                error_count += 1

        # Log result
        logger.info(f"Rename Complete: Successfully renamed: {success_count} file(s), Errors: {error_count} file(s)")

        # Update and reload folder without losing state
        if success_count > 0:
            # We don't clear suggestions entirely. We migrate the renamed ones.
            # Any non-renamed files will keep their suggestions.
            for old_path, suggestion in selected:
                if str(Path(old_path).parent / suggestion.filename) in migrated_suggestions:
                    self.suggestions.pop(old_path, None)
            
            # Merge migrated suggestions back
            self.suggestions.update(migrated_suggestions)
            
            # Force a re-scan of the folder to update self.files and the list model
            # but preserve our current self.suggestions
            current_folder = self.files[0].parent if self.files else None
            if current_folder:
                self._refresh_folder_preserving_state(str(current_folder))

    def _execute_move(self):
        """Move selected files to their suggested destinations."""
        selected = self._get_selected_files()

        if not selected:
            QMessageBox.warning(
                self,
                "No Files Selected",
                "Please select files and process them first.",
            )
            return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Confirm Rename and Move",
            f"This will rename and move {len(selected)} file(s) to their suggested destinations.\n"
            "This operation cannot be undone.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Execute move operations
        success_count = 0
        error_count = 0

        for file_path_str, suggestion in selected:
            # Skip if destination is empty
            if not suggestion.destination:
                logger.info(f"Skipping {file_path_str} (no destination)")
                continue

            file_path = Path(file_path_str)
            base_dir = self.config.default_dest_base or file_path.parent

            # Construct destination path
            dest_dir = Path(base_dir) / suggestion.destination
            dest_path = dest_dir / suggestion.filename

            try:
                # Create destination directory if needed
                dest_dir.mkdir(parents=True, exist_ok=True)

                if dest_path.exists() and dest_path != file_path:
                    logger.warning(f"Target file already exists: {dest_path}")
                    error_count += 1
                    continue

                # Move/rename file
                file_path.rename(dest_path)
                logger.info(f"Moved {file_path} -> {dest_path}")
                success_count += 1

            except Exception as e:
                logger.error(f"Failed to move {file_path}: {e}", exc_info=True)
                error_count += 1

        # Log result
        logger.info(f"Move Complete: Successfully moved: {success_count} file(s), Errors: {error_count} file(s)")

        # Reload folder
        if success_count > 0:
            current_folder = self.files[0].parent if self.files else None
            if current_folder:
                self._load_folder(str(current_folder))

    def _refresh_folder_preserving_state(self, folder_path: str):
        """Reload folder contents without clearing existing suggestions.
        
        Args:
            folder_path: Path to the folder.
        """
        folder = Path(folder_path)
        logger.debug(f"Refreshing folder: {folder}")

        # Find all supported files
        patterns = ["*.pdf", "*.png", "*.jpg", "*.jpeg", "*.tiff", "*.tif", "*.bmp"]
        self.files = []

        for pattern in patterns:
            self.files.extend(folder.glob(pattern))

        # Update file list model but keep self.suggestions!
        self.file_list_model.clear()

        for file_path in self.files:
            file_str = str(file_path)
            item = QStandardItem(file_path.name)
            item.setCheckable(True)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(file_str, Qt.ItemDataRole.UserRole)
            
            # Mark processed/state
            if file_str in self.suggestions:
                res = self.suggestions[file_str]
                if isinstance(res, FilingSuggestion):
                    item.setText(f"✓ {file_path.name}")
                elif isinstance(res, Exception):
                    item.setText(f"❌ {file_path.name}")
            else:
                # New file or one we lost state for
                self.suggestions[file_str] = FilingSuggestion(
                    filename=file_path.name,
                    destination="",
                    confidence=1.0,
                    reasoning="Refreshed"
                )
            
            self.file_list_model.appendRow(item)

        if self.files:
            # Re-select the same index if valid, else first
            new_index = self.current_file_index if 0 <= self.current_file_index < len(self.files) else 0
            first_index = self.file_list_model.index(new_index, 0)
            self.file_list.setCurrentIndex(first_index)

    def _generate_context(self):
        """Generate filing context from the organized documents directory."""
        if not self.config or not self.config.source_dir:
            QMessageBox.warning(
                self,
                "Configuration Missing",
                "SOURCE_DIR is not set in your .env file. Please set it to your organized documents root."
            )
            return

        source_path = Path(self.config.source_dir)
        if not source_path.exists():
            QMessageBox.critical(
                self,
                "Directory Not Found",
                f"SOURCE_DIR does not exist: {source_path}"
            )
            return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Confirm Context Generation",
            f"This will scan {source_path} and use an LLM to update your filing conventions.\n\n"
            "This may take a minute and will consume API tokens.\n\n"
            "Do you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Disable UI
        self.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress

        # Start thread
        self.context_thread = ContextGenerationThread(source_path)
        self.context_thread.finished.connect(self._on_context_generated)
        self.context_thread.start()

    def _on_context_generated(self, result):
        """Handle completion of context generation."""
        self.setEnabled(True)
        self.progress_bar.setVisible(False)

        if isinstance(result, Exception):
            QMessageBox.critical(
                self,
                "Context Generation Failed",
                f"An error occurred while generating context:\n{result}"
            )
        else:
            QMessageBox.information(
                self,
                "Context Updated",
                "Filing context has been successfully updated and saved to src/data/context.md.\n\n"
                "The new conventions will be used for future document analysis."
            )
            
            # Refresh VLM service with new context
            try:
                self.vlm_service = create_vlm_service(self.config)
                logger.info("VLM service refreshed with new context")
            except Exception as e:
                logger.error(f"Failed to refresh VLM service: {e}")



def main():
    """Main entry point for the GUI application."""

    # Configure Qt platform for different environments
    if not os.environ.get('QT_QPA_PLATFORM'):
        if os.environ.get('DISPLAY'):
            # X server is available (e.g., X410) - use xcb (X11) explicitly
            # This prevents Qt from trying Wayland first, which X410 doesn't support
            os.environ['QT_QPA_PLATFORM'] = 'xcb'
        else:
            # No display server - use offscreen rendering
            os.environ['QT_QPA_PLATFORM'] = 'offscreen'

    # Configure logging to both file and console
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_filename = os.path.join(
        log_dir,
        f"docfiler_gui_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

    # Create formatters and handlers
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # File handler
    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logger.info(f"Logging to file: {log_filename}")
    logger.info("Starting Document Filer GUI")

    # Create application
    app = QApplication(sys.argv)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Set up signal handler for graceful shutdown on Ctrl-C
    def signal_handler(signum, frame):
        """Handle Ctrl-C gracefully."""
        logger.info("Received interrupt signal, shutting down gracefully...")
        app.quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Allow Ctrl-C to work by setting up a timer to process events
    # This is needed because Qt event loop blocks signal handling
    timer = app.startTimer(500)  # Check for signals every 500ms

    # Run application
    try:
        exit_code = app.exec()
        logger.info("Application exited normally")
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
