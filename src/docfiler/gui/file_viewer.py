"""File viewer widget for Document Filer GUI.

Shows a zoomable preview of one document plus its editable filing suggestion.
"""

import logging
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..image_processor import IMAGE_EXTENSIONS, ImageProcessor

logger = logging.getLogger(__name__)

# Preview rendering: ~2000px leaves headroom for zooming without huge memory use
PREVIEW = ImageProcessor(target_dpi=150, max_dimension=2000)


def _pil_to_qpixmap(img: Image.Image) -> QPixmap:
    pixmap = QPixmap()
    pixmap.loadFromData(PREVIEW._image_to_bytes(img))
    return pixmap


def _load_preview_image(path: Path) -> Image.Image:
    """Load a preview image for an image file or the first page of a PDF."""
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        return PREVIEW.load_image(path)
    if path.suffix.lower() != ".pdf":
        raise ValueError("Preview not available for this file type")
    try:
        return PREVIEW.render_pdf_page(path, 0)
    except Exception as e:
        # Fallback when poppler is unavailable: first embedded image on page 1
        logger.warning(f"pdf2image failed for {path.name}: {e}; trying embedded images")
        pages = PdfReader(path).pages
        if not pages or not pages[0].images:
            raise ValueError(f"Could not render PDF and no embedded images found ({e})") from e
        return PREVIEW._resize_image(pages[0].images[0].image.convert("RGB"))


def _set_text_show_start(edit: QLineEdit, text: str) -> None:
    """Set text and scroll to its start, so overflowing text shows its beginning."""
    edit.setText(text)
    edit.setCursorPosition(0)


class FileViewerWidget(QWidget):
    """Widget to display and edit a single document's filing information."""

    destination_changed = pyqtSignal(str)  # user edited the destination
    filename_changed = pyqtSignal(str)  # user edited the filename

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dest_base: str | None = None  # base dir for Browse... and relative paths
        self._full_pixmap = QPixmap()
        self._zoom_factor = 1.0
        self._fit_to_view = True
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Preview area (scrollable and zoomable; we size the label ourselves)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #f0f0f0; border: 1px solid #ccc; }")
        self.scroll_area.setMinimumSize(400, 400)
        self.preview_label = QLabel("No file selected")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.scroll_area.setWidget(self.preview_label)
        layout.addWidget(self.scroll_area)

        def row(label: str, *widgets) -> None:
            h = QHBoxLayout()
            h.addWidget(QLabel(label))
            for w in widgets:
                h.addWidget(w)
            layout.addLayout(h)

        self.original_label = QLabel("-")
        self.original_label.setStyleSheet("QLabel { font-weight: bold; }")
        self.original_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row("Original:", self.original_label)

        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("Suggested filename will appear here")
        self.filename_edit.textEdited.connect(self.filename_changed.emit)
        row("Filename:", self.filename_edit)

        self.dest_edit = QLineEdit()
        self.dest_edit.setPlaceholderText("Suggested destination (empty = don't move)")
        self.dest_edit.textEdited.connect(self.destination_changed.emit)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._on_browse_clicked)
        row("Destination:", self.dest_edit, browse_button)

        self.confidence_label = QLabel("Confidence: -")
        layout.addWidget(self.confidence_label)
        self.reasoning_label = QLabel("Reasoning: -")
        self.reasoning_label.setWordWrap(True)
        layout.addWidget(self.reasoning_label)

        buttons = QHBoxLayout()
        skip_button = QPushButton("Skip Move (clear destination)")
        skip_button.setToolTip("Files with an empty destination are not moved")
        skip_button.clicked.connect(lambda: self._set_destination(""))
        buttons.addWidget(skip_button)
        buttons.addStretch()
        for text, width, slot in (("+", 30, self.zoom_in), ("-", 30, self.zoom_out), ("Fit", 50, self.reset_zoom)):
            b = QPushButton(text)
            b.setFixedWidth(width)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        layout.addLayout(buttons)

    # --- content -------------------------------------------------------------

    def set_file(self, file_path: str | Path):
        """Show the preview for a file."""
        path = Path(file_path)
        self.original_label.setText(path.name)
        try:
            pixmap = _pil_to_qpixmap(_load_preview_image(path))
            if pixmap.isNull():
                raise ValueError("Failed to create preview image")
        except Exception as e:
            logger.warning(f"Preview failed for {path}: {e}")
            self._full_pixmap = QPixmap()
            self.preview_label.setText(f"{path.name}\n(Preview not available: {e})")
            return
        self._full_pixmap = pixmap
        self._fit_to_view = True
        self._update_preview()

    def set_suggestion(self, filename: str, destination: str, confidence: float, reasoning: str):
        """Display a suggestion (programmatic: does not emit *_changed signals)."""
        _set_text_show_start(self.filename_edit, filename)
        _set_text_show_start(self.dest_edit, destination)
        self.confidence_label.setText(f"Confidence: {confidence:.1%}")
        self.reasoning_label.setText(f"Reasoning: {reasoning}")

    def clear_suggestion(self, reason: str = "-"):
        """Clear the suggestion fields."""
        self.filename_edit.clear()
        self.dest_edit.clear()
        self.confidence_label.setText("Confidence: -")
        self.reasoning_label.setText(f"Reasoning: {reason}")

    def set_conflict(self, reason: str | None):
        """Highlight the filename in red when its new name is already taken."""
        self.filename_edit.setStyleSheet("QLineEdit { background-color: #f4b4b4; color: black; }" if reason else "")
        self.filename_edit.setToolTip(f"Cannot move: {reason}. Rename it." if reason else "")

    def get_filename(self) -> str:
        return self.filename_edit.text()

    def get_destination(self) -> str:
        return self.dest_edit.text()

    def _set_destination(self, text: str):
        """Set destination as a user edit (emits destination_changed)."""
        _set_text_show_start(self.dest_edit, text)
        self.destination_changed.emit(text)

    def _on_browse_clicked(self):
        base = Path(self.dest_base) if self.dest_base else Path.home()
        start_dir = base
        if current := self.dest_edit.text().strip():
            if (base / current).exists():
                start_dir = base / current

        folder = QFileDialog.getExistingDirectory(
            self, "Select Destination Folder", str(start_dir), QFileDialog.Option.ShowDirsOnly
        )
        if not folder:
            return
        folder_path = Path(folder)
        try:
            self._set_destination(str(folder_path.relative_to(base)) if self.dest_base else str(folder_path))
        except ValueError:
            self._set_destination(str(folder_path))  # outside dest_base: keep absolute

    # --- zoom ----------------------------------------------------------------

    def _update_preview(self):
        """Redraw the preview for the current zoom / fit settings."""
        if self._full_pixmap.isNull():
            return
        if self._fit_to_view:
            target = self.scroll_area.viewport().size()
        else:
            target = self._full_pixmap.size() * self._zoom_factor
        scaled = self._full_pixmap.scaled(
            target, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        if self._fit_to_view:
            self._zoom_factor = scaled.width() / self._full_pixmap.width()
        self.preview_label.setPixmap(scaled)
        self.preview_label.resize(scaled.size())

    def _zoom(self, factor: float):
        self._fit_to_view = False
        self._zoom_factor = max(0.1, self._zoom_factor * factor)
        self._update_preview()

    def zoom_in(self):
        self._zoom(1.2)

    def zoom_out(self):
        self._zoom(1 / 1.2)

    def reset_zoom(self):
        self._fit_to_view = True
        self._update_preview()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_to_view:
            self._update_preview()

    def wheelEvent(self, event):
        """Ctrl + mouse wheel zooms."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_in() if event.angleDelta().y() > 0 else self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)
