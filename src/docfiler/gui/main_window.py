"""Main window for Document Filer GUI.

File table (checkbox, suggested name, confidence) on the left, preview/suggestion
editor on the right.
Analysis and context generation run in background threads.
"""

import filecmp
import logging
import os
import shutil
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PyQt6.QtCore import (
    QMessageLogContext,
    Qt,
    QThread,
    QTimer,
    QtMsgType,
    pyqtSignal,
    qInstallMessageHandler,
)
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..api_clients import classify_api_error
from ..cache_manager import CacheManager, create_cache_manager
from ..cli.context_generator import generate_context
from ..config import CLI_PROVIDERS, PROVIDERS, Config, load_config, setup_logging
from ..image_processor import list_documents
from ..models import FilingSuggestion
from ..vlm_service import VLMService, create_vlm_service
from .file_viewer import FileViewerWidget

logger = logging.getLogger(__name__)

PATH_ROLE = Qt.ItemDataRole.UserRole
COL_FILE, COL_NEW_NAME, COL_CONFIDENCE = range(3)
COLUMN_TITLES = ("File", "New Name", "Conf.")


def unique_path(target: Path) -> Path:
    """Return target, or 'stem (2).ext', 'stem (3).ext', ... if it already exists."""
    candidate, n = target, 2
    while candidate.exists():
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        n += 1
    return candidate


def display_name(suggestion: FilingSuggestion) -> str:
    """Suggested 'destination/filename' (just the filename when not moving)."""
    if not suggestion.destination:
        return suggestion.filename
    return f"{suggestion.destination.rstrip('/')}/{suggestion.filename}"


class CheckableTableView(QTableView):
    """QTableView where shift-click toggles the column-0 checkboxes for a whole range."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_index = None

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        model = self.model()
        shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        if not (index.isValid() and shift and self.last_index is not None and self.last_index.isValid()):
            super().mousePressEvent(event)
            if index.isValid():
                self.last_index = index
            return

        target = model.item(index.row(), COL_FILE)
        old_state = target.checkState()
        super().mousePressEvent(event)
        new_state = target.checkState()
        if new_state == old_state:  # clicked the text, not the box: toggle anyway
            new_state = Qt.CheckState.Unchecked if old_state == Qt.CheckState.Checked else Qt.CheckState.Checked

        lo, hi = sorted((self.last_index.row(), index.row()))
        for row in range(lo, hi + 1):
            model.item(row, COL_FILE).setCheckState(new_state)
        self.last_index = index


class ProcessingThread(QThread):
    """Analyzes documents in the background; emits one result per file."""

    file_processed = pyqtSignal(str, object)  # file path, FilingSuggestion or Exception

    def __init__(self, files: list[Path], vlm_service: VLMService, max_parallel: int = 1):
        super().__init__()
        self.files = files
        self.vlm_service = vlm_service
        self.max_parallel = max_parallel

    def run(self):
        with ThreadPoolExecutor(max_workers=self.max_parallel) as executor:
            futures = {executor.submit(self.vlm_service.analyze_document, fp): fp for fp in self.files}
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as e:
                    result = e
                self.file_processed.emit(str(futures[future]), result)


class ContextGenerationThread(QThread):
    """Generates filing context in the background."""

    result = pyqtSignal(object)  # context str or Exception

    def __init__(self, source_path: Path, config: Config):
        super().__init__()
        self.source_path = source_path
        self.config = config

    def run(self):
        try:
            self.result.emit(generate_context(self.source_path, self.config))
        except Exception as e:
            logger.error(f"Error generating context: {e}")
            self.result.emit(e)


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.config: Config | None = None
        self.vlm_service: VLMService | None = None
        self.cache_manager: CacheManager | None = None
        self.current_folder: Path | None = None
        self.files: list[Path] = []
        self.suggestions: dict[str, FilingSuggestion | Exception] = {}  # str(path) -> result
        self.file_hashes: dict[str, str] = {}  # str(path) -> sha256
        self.current_file_index = -1
        self.processing_thread: ProcessingThread | None = None
        self.context_thread: ContextGenerationThread | None = None
        self._batch_done = 0
        self._batch_errors = 0

        self._init_ui()
        self._load_config()

        if self.config.input_dir and Path(self.config.input_dir).is_dir():
            self._load_folder(Path(self.config.input_dir))

    # --- setup -----------------------------------------------------------------

    def _init_ui(self):
        self.setWindowTitle("Document Filer")
        self.setMinimumSize(1000, 700)
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        left_panel = QWidget()
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(0, 0, 0, 0)

        def button(text: str, slot, tooltip: str = "") -> QPushButton:
            b = QPushButton(text)
            b.clicked.connect(slot)
            b.setToolTip(tooltip)
            return b

        provider_row = QHBoxLayout()
        provider_row.addWidget(QLabel("Provider:"))
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(PROVIDERS)
        self.provider_combo.setToolTip(
            "claude-cli / codex-cli use your logged-in Claude Code / Codex CLI "
            "(subscription); the others use API keys from .env"
        )
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        provider_row.addWidget(self.provider_combo, 1)
        left.addLayout(provider_row)

        self.open_button = button("Open Folder...", self._open_folder)
        left.addWidget(self.open_button)

        self.file_list_model = QStandardItemModel(0, len(COLUMN_TITLES))
        self.file_list_model.setHorizontalHeaderLabels(COLUMN_TITLES)
        self.file_list = CheckableTableView()
        self.file_list.setModel(self.file_list_model)
        self.file_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.file_list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_list.setTextElideMode(Qt.TextElideMode.ElideRight)  # overflow keeps the start visible
        self.file_list.setWordWrap(False)
        self.file_list.verticalHeader().setVisible(False)
        self.file_list.verticalHeader().setDefaultSectionSize(self.fontMetrics().height() + 8)
        header = self.file_list.horizontalHeader()
        header.setSectionResizeMode(COL_FILE, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(COL_NEW_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_CONFIDENCE, QHeaderView.ResizeMode.ResizeToContents)
        self.file_list.setColumnWidth(COL_FILE, 180)
        self.file_list.selectionModel().currentChanged.connect(self._on_file_selected)
        left.addWidget(self.file_list)

        selection_row = QHBoxLayout()
        selection_row.addWidget(button("Select All", lambda: self._set_all_checked(True)))
        selection_row.addWidget(button("Select None", lambda: self._set_all_checked(False)))
        left.addLayout(selection_row)

        self.process_button = button("Process Selected Files", self._process_selected)
        self.context_button = button(
            "Generate Filing Context", self._generate_context,
            "Analyze organized documents to update filing conventions",
        )
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.rename_button = button("Rename Selected Files (in place)", lambda: self._execute(move=False))
        self.move_button = button("Rename and Move Selected Files", lambda: self._execute(move=True))
        for w in (self.process_button, self.context_button, self.progress_bar, self.rename_button, self.move_button):
            left.addWidget(w)

        self.file_viewer = FileViewerWidget()
        self.file_viewer.filename_changed.connect(lambda text: self._on_viewer_edited(filename=text))
        self.file_viewer.destination_changed.connect(lambda text: self._on_viewer_edited(destination=text))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.file_viewer)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([600, 600])
        main_layout.addWidget(splitter)

    def _load_config(self):
        """Load configuration and create services; exit on failure."""
        try:
            self.config = load_config()
            self.cache_manager = create_cache_manager()
            self.vlm_service = create_vlm_service(self.config, cache_manager=self.cache_manager)
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            QMessageBox.critical(
                self, "Configuration Error", f"Failed to load configuration:\n{e}\n\nPlease check your .env file."
            )
            sys.exit(1)

        logger.info(f"Configuration loaded: Provider={self.config.vlm_provider}")
        self.file_viewer.dest_base = self.config.dest_base
        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentText(self.config.vlm_provider)
        self.provider_combo.blockSignals(False)

    def _on_provider_changed(self, provider: str):
        """Switch the VLM provider; revert the dropdown if it is not usable."""
        try:
            config = self.config.with_provider(provider)
            service = create_vlm_service(config, cache_manager=self.cache_manager)
        except Exception as e:
            hint = "" if provider in CLI_PROVIDERS else "\n\nAdd the API key to .env and restart."
            QMessageBox.warning(self, "Provider Unavailable", f"Cannot use {provider}:\n{e}{hint}")
            self.provider_combo.blockSignals(True)
            self.provider_combo.setCurrentText(self.config.vlm_provider)
            self.provider_combo.blockSignals(False)
            return
        self.config, self.vlm_service = config, service
        logger.info(f"Switched provider to {provider} ({config.active_model or 'CLI default model'})")

    def _set_busy(self, busy: bool):
        """Disable actions that must not run concurrently with background work."""
        for w in (self.process_button, self.context_button, self.rename_button,
                  self.move_button, self.open_button, self.provider_combo):
            w.setEnabled(not busy)

    # --- folder & list -----------------------------------------------------------

    def _open_folder(self):
        start = self.current_folder or self.config.input_dir or str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder with Documents", str(start), QFileDialog.Option.ShowDirsOnly
        )
        if folder:
            self._load_folder(Path(folder))

    def _load_folder(self, folder: Path):
        """(Re)load the file list, keeping in-memory results and restoring cached ones."""
        logger.info(f"Loading folder: {folder}")
        self.current_folder = folder
        self.files = list_documents(folder)
        self.file_list_model.removeRows(0, self.file_list_model.rowCount())
        self.file_list.last_index = None

        for path in self.files:
            key = str(path)
            item = QStandardItem(path.name)
            item.setCheckable(True)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(key, PATH_ROLE)
            item.setToolTip(path.name)
            confidence = QStandardItem()
            confidence.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.file_list_model.appendRow([item, QStandardItem(), confidence])

            if key not in self.file_hashes:
                try:
                    self.file_hashes[key] = self.cache_manager.compute_hash(path)
                except OSError as e:
                    logger.warning("Could not hash %s: %s", path.name, e)
            if key not in self.suggestions and (h := self.file_hashes.get(key)):
                if cached := self.cache_manager.get_cached_result(h):
                    self.suggestions[key] = cached
            self._update_item_status(key)

        logger.info(f"Found {len(self.files)} files")
        if self.files:
            row = self.current_file_index if 0 <= self.current_file_index < len(self.files) else 0
            self.file_list.setCurrentIndex(self.file_list_model.index(row, 0))
        else:
            self.current_file_index = -1
            self.file_viewer.clear_suggestion()

    def _row_for_path(self, key: str) -> int | None:
        for row in range(self.file_list_model.rowCount()):
            if self.file_list_model.item(row, COL_FILE).data(PATH_ROLE) == key:
                return row
        return None

    def _update_item_status(self, key: str):
        """Refresh a row: ✓/❌ marker, suggested new name, and confidence."""
        row = self._row_for_path(key)
        if row is None:
            return
        result = self.suggestions.get(key)
        model = self.file_list_model
        marker = "✓ " if isinstance(result, FilingSuggestion) else "❌ " if isinstance(result, Exception) else ""
        model.item(row, COL_FILE).setText(marker + Path(key).name)
        new_name = model.item(row, COL_NEW_NAME)
        confidence = model.item(row, COL_CONFIDENCE)
        if isinstance(result, FilingSuggestion):
            new_name.setText(display_name(result))
            new_name.setToolTip(display_name(result))
            confidence.setText(f"{result.confidence:.0%}")
        else:
            error = self._error_message(result) if isinstance(result, Exception) else ""
            new_name.setText(error)
            new_name.setToolTip(error)
            confidence.setText("")

    def _checked_paths(self) -> list[str]:
        return [
            item.data(PATH_ROLE)
            for row in range(self.file_list_model.rowCount())
            if (item := self.file_list_model.item(row, COL_FILE)).checkState() == Qt.CheckState.Checked
        ]

    def _set_all_checked(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.file_list_model.rowCount()):
            self.file_list_model.item(row, COL_FILE).setCheckState(state)

    def _on_file_selected(self, current, _previous):
        if not current.isValid() or current.row() >= len(self.files):
            return
        self.current_file_index = current.row()
        path = self.files[current.row()]
        self.file_viewer.set_file(path)
        self._show_result(str(path))

    def _show_result(self, key: str):
        result = self.suggestions.get(key)
        if isinstance(result, FilingSuggestion):
            self.file_viewer.set_suggestion(result.filename, result.destination, result.confidence, result.reasoning)
        elif isinstance(result, Exception):
            self.file_viewer.clear_suggestion(f"Analysis failed: {self._error_message(result)}")
        else:
            self.file_viewer.clear_suggestion("Not processed yet")

    def _current_key(self) -> str | None:
        if 0 <= self.current_file_index < len(self.files):
            return str(self.files[self.current_file_index])
        return None

    def _on_viewer_edited(self, filename: str | None = None, destination: str | None = None):
        """Apply a manual edit to the current file's suggestion and persist it."""
        key = self._current_key()
        if key is None:
            return
        suggestion = self.suggestions.get(key)
        if not isinstance(suggestion, FilingSuggestion):
            suggestion = FilingSuggestion(
                filename=self.file_viewer.get_filename() or Path(key).name,
                destination=self.file_viewer.get_destination(),
                confidence=1.0,
                reasoning="Manual entry",
            )
            self.suggestions[key] = suggestion
        if filename is not None:
            suggestion.filename = filename
        if destination is not None:
            suggestion.destination = destination
        self._update_item_status(key)
        if file_hash := self.file_hashes.get(key):
            self.cache_manager.save_gui_state(file_hash, suggestion.filename, suggestion.destination)

    def _error_message(self, exc: Exception) -> str:
        return classify_api_error(self.config.vlm_provider, exc)

    # --- analysis ------------------------------------------------------------------

    def _process_selected(self):
        checked = self._checked_paths()
        if not checked:
            QMessageBox.warning(self, "No Selection", "Please check at least one file to process.")
            return

        to_process = [Path(k) for k in checked if not self.cache_manager.has_entry(self.file_hashes.get(k))]
        skipped = len(checked) - len(to_process)
        if skipped:
            logger.info("Skipping %d cached file(s), processing %d", skipped, len(to_process))
        if not to_process:
            QMessageBox.information(
                self, "All Cached",
                f"All {skipped} selected file(s) already have results.\nDelete cache/ to force reprocessing.",
            )
            return

        self._set_busy(True)
        self.progress_bar.setRange(0, len(to_process))
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self._batch_done = self._batch_errors = 0

        self.processing_thread = ProcessingThread(to_process, self.vlm_service, self.config.vlm_max_parallel)
        self.processing_thread.file_processed.connect(self._on_file_processed)
        self.processing_thread.finished.connect(self._on_processing_finished)
        self.processing_thread.start()

    def _on_file_processed(self, key: str, result):
        self._batch_done += 1
        self.progress_bar.setValue(self._batch_done)
        if isinstance(result, Exception):
            self._batch_errors += 1
            logger.error(f"Error processing {key}: {self._error_message(result)}")
        self.suggestions[key] = result
        self._update_item_status(key)
        if key == self._current_key():
            self._show_result(key)

    def _on_processing_finished(self):
        self.progress_bar.setVisible(False)
        self._set_busy(False)
        ok = self._batch_done - self._batch_errors
        logger.info(f"Processing complete: {ok} successful, {self._batch_errors} failed")
        if self._batch_errors:
            QMessageBox.warning(
                self, "Processing Finished With Errors",
                f"{ok} file(s) succeeded, {self._batch_errors} failed (marked ❌). See the log for details.",
            )

    # --- rename / move ---------------------------------------------------------------

    def _target_path(self, source: Path, suggestion: FilingSuggestion, move: bool) -> Path | None:
        """Where a file should go, or None if there is nothing to do."""
        if not suggestion.filename or Path(suggestion.filename).name != suggestion.filename:
            raise ValueError(f"invalid filename {suggestion.filename!r}")
        if not move:
            return source.parent / suggestion.filename
        if not suggestion.destination:
            return None  # skipped: no destination
        base = Path(self.config.dest_base) if self.config.dest_base else source.parent
        return base / Path(suggestion.destination).expanduser() / suggestion.filename

    def _execute(self, move: bool):
        """Rename (move=False) or rename-and-move (move=True) checked files."""
        selected = [(k, s) for k in self._checked_paths() if isinstance(s := self.suggestions.get(k), FilingSuggestion)]
        if not selected:
            QMessageBox.warning(self, "No Files Selected", "Please select files and process them first.")
            return

        action = "rename and move" if move else "rename"
        where = "to their suggested destinations" if move else "in their current location"
        reply = QMessageBox.question(
            self, f"Confirm {action.title()}",
            f"This will {action} {len(selected)} file(s) {where}.\n"
            "This operation cannot be undone.\n\nAre you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        done, skipped, errors = 0, 0, []
        for key, suggestion in selected:
            source = Path(key)
            try:
                target = self._target_path(source, suggestion, move)
                if target is None or target == source:
                    logger.debug(f"Skipping {source}: nothing to {action}")
                    skipped += 1
                    continue
                if target.exists():
                    if target.is_file() and filecmp.cmp(source, target, shallow=False):
                        raise FileExistsError(f"identical file already exists: {target}")
                    unique = unique_path(target)
                    logger.warning(f"{target} already exists; using {unique.name}")
                    target = unique
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(source, target)  # works across filesystems, unlike Path.rename
            except Exception as e:
                logger.error(f"Failed to {action} {source}: {e}", exc_info=not isinstance(e, (OSError, ValueError)))
                errors.append(f"{source.name}: {e}")
                continue

            logger.info(f"{'Moved' if move else 'Renamed'} {source} -> {target}")
            done += 1
            # Carry state over to the new path (moved files simply leave the list)
            self.suggestions[str(target)] = self.suggestions.pop(key)
            if key in self.file_hashes:
                self.file_hashes[str(target)] = self.file_hashes.pop(key)

        logger.info(f"{action.title()} complete: {done} done, {skipped} skipped, {len(errors)} failed")
        if errors:
            QMessageBox.warning(self, f"{action.title()} Errors", "\n".join(errors[:20]))
        if done and self.current_folder:
            self._load_folder(self.current_folder)

    # --- context generation ---------------------------------------------------------

    def _generate_context(self):
        if not self.config.source_dir:
            QMessageBox.warning(
                self, "Configuration Missing",
                "SOURCE_DIR is not set in your .env file. Please set it to your organized documents root.",
            )
            return
        source_path = Path(self.config.source_dir)
        if not source_path.is_dir():
            QMessageBox.critical(self, "Directory Not Found", f"SOURCE_DIR does not exist: {source_path}")
            return

        reply = QMessageBox.question(
            self, "Confirm Context Generation",
            f"This will scan {source_path} and use {self.config.vlm_provider} to update your "
            "filing conventions.\n\nThis may take a minute.\n\nDo you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True)
        self.progress_bar.setRange(0, 0)  # indeterminate
        self.progress_bar.setVisible(True)
        self.context_thread = ContextGenerationThread(source_path, self.config)
        self.context_thread.result.connect(self._on_context_generated)
        self.context_thread.start()

    def _on_context_generated(self, result):
        self.progress_bar.setVisible(False)
        self._set_busy(False)
        if isinstance(result, Exception):
            QMessageBox.critical(self, "Context Generation Failed", self._error_message(result))
            return
        try:
            self.vlm_service = create_vlm_service(self.config, cache_manager=self.cache_manager)
            logger.info("VLM service refreshed with new context")
        except Exception as e:
            logger.error(f"Failed to refresh VLM service: {e}")
        QMessageBox.information(
            self, "Context Updated",
            "Filing context has been updated and saved to src/data/context.md.\n\n"
            "The new conventions will be used for future document analysis.",
        )

    def closeEvent(self, event):
        """Wait for background threads so Qt does not abort on exit."""
        for thread in (self.processing_thread, self.context_thread):
            if thread and thread.isRunning():
                logger.info("Waiting for background work to finish...")
                thread.wait()
        super().closeEvent(event)


_QT_LOG_LEVELS = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}


def _qt_message_handler(msg_type: QtMsgType, _context: QMessageLogContext, message: str) -> None:
    """Send Qt's own diagnostics through Python logging."""
    logging.getLogger("qt").log(_QT_LOG_LEVELS.get(msg_type, logging.INFO), message)


def main():
    """Main entry point for the GUI application."""
    # X410 / WSL2: force X11 when a display exists, otherwise render offscreen
    if not os.environ.get("QT_QPA_PLATFORM"):
        os.environ["QT_QPA_PLATFORM"] = "xcb" if os.environ.get("DISPLAY") else "offscreen"

    log_file = setup_logging("docfiler_gui")
    qInstallMessageHandler(_qt_message_handler)
    logger.info(f"Logging to file: {log_file}")
    logger.info("Starting Document Filer GUI")

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    # Ctrl-C: Python signal handlers only run when the interpreter gets control,
    # so a no-op Python timer callback wakes it up periodically.
    signal.signal(signal.SIGINT, lambda *_: (logger.info("Interrupted, shutting down..."), app.quit()))
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
