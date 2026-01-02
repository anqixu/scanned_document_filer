"""Main window for Document Filer GUI.

This module provides the main application window with file browsing and
batch processing capabilities.
"""

import logging
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..config import load_config
from ..vlm_service import FilingSuggestion, create_vlm_service
from .file_viewer import FileViewerWidget

logger = logging.getLogger(__name__)


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
                self.file_processed.emit(file_path, suggestion)
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                self.file_processed.emit(file_path, e)

            self.progress.emit(idx, total)

        self.finished.emit()


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

        # File list
        self.file_list = QListWidget()
        self.file_list.currentRowChanged.connect(self._on_file_selected)
        left_panel.addWidget(self.file_list)

        # Processing controls
        process_button = QPushButton("Process All Files")
        process_button.clicked.connect(self._process_all)
        left_panel.addWidget(process_button)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_panel.addWidget(self.progress_bar)

        # Execute button
        execute_button = QPushButton("Move/Rename Files")
        execute_button.clicked.connect(self._execute_filing)
        left_panel.addWidget(execute_button)

        main_layout.addLayout(left_panel, 1)

        # Right panel - file viewer
        self.file_viewer = FileViewerWidget()
        main_layout.addWidget(self.file_viewer, 2)

    def _load_config(self):
        """Load application configuration."""
        try:
            self.config = load_config()
            logger.info(f"Configuration loaded: Provider={self.config.vlm_provider}")

            # Create VLM service
            self.vlm_service = create_vlm_service(self.config)

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
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder with Documents",
            "",
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
        self.file_list.clear()
        self.suggestions.clear()

        for file_path in self.files:
            item = QListWidgetItem(file_path.name)
            item.setData(1, str(file_path))  # Store full path
            self.file_list.addItem(item)

        if self.files:
            self.file_list.setCurrentRow(0)

    def _on_file_selected(self, index: int):
        """Handle file selection in the list.

        Args:
            index: Index of the selected file.
        """
        if index < 0 or index >= len(self.files):
            return

        self.current_file_index = index
        file_path = self.files[index]

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

    def _process_all(self):
        """Process all files in the list."""
        if not self.files:
            QMessageBox.warning(self, "No Files", "Please open a folder first.")
            return

        # Disable UI during processing
        self.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.files))
        self.progress_bar.setValue(0)

        # Start processing thread
        self.processing_thread = ProcessingThread(self.files, self.vlm_service)
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
            # Mark as error in the list
            for i in range(self.file_list.count()):
                item = self.file_list.item(i)
                if item.data(1) == file_path:
                    item.setText(f"❌ {Path(file_path).name}")
                    break
        else:
            # Store suggestion
            self.suggestions[file_path] = result

            # Update list item
            for i in range(self.file_list.count()):
                item = self.file_list.item(i)
                if item.data(1) == file_path:
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
        self.setEnabled(True)

        QMessageBox.information(
            self,
            "Processing Complete",
            f"Processed {len(self.files)} files.\n"
            f"Successful: {len(self.suggestions)}\n"
            f"Errors: {len(self.files) - len(self.suggestions)}",
        )

    def _execute_filing(self):
        """Execute the file moving/renaming operations."""
        if not self.suggestions:
            QMessageBox.warning(
                self,
                "No Suggestions",
                "Please process files first before executing.",
            )
            return

        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Confirm File Operations",
            f"This will move/rename {len(self.suggestions)} files.\n"
            "This operation cannot be undone.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Execute file operations
        success_count = 0
        error_count = 0

        for file_path_str, suggestion in self.suggestions.items():
            if not isinstance(suggestion, FilingSuggestion):
                continue

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

                # Move/rename file
                file_path.rename(dest_path)
                logger.info(f"Moved {file_path} -> {dest_path}")
                success_count += 1

            except Exception as e:
                logger.error(f"Failed to move {file_path}: {e}")
                error_count += 1

        # Show result
        QMessageBox.information(
            self,
            "Filing Complete",
            f"Successfully moved: {success_count} files\n" f"Errors: {error_count} files",
        )

        # Reload folder if we're using same base
        if success_count > 0:
            self.file_list.clear()
            self.files.clear()
            self.suggestions.clear()


def main():
    """Main entry point for the GUI application."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create application
    app = QApplication(sys.argv)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
