"""File viewer widget for Document Filer GUI.

This module provides a widget to display and edit document filing information.
"""

import io
import logging
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

# Support high-resolution scans by increasing the decompression bomb limit (approx 200MP)
Image.MAX_IMAGE_PIXELS = 200_000_000

from pdf2image import convert_from_path
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

logger = logging.getLogger(__name__)


class FileViewerWidget(QWidget):
    """Widget to display and edit a single document's filing information."""

    # Signals
    skip_toggled = pyqtSignal(bool)  # Emitted when skip state changes
    destination_changed = pyqtSignal(str)  # Emitted when destination is edited
    filename_changed = pyqtSignal(str)  # Emitted when filename is edited

    def __init__(self, parent=None):
        """Initialize the file viewer widget."""
        super().__init__(parent)
        self.source_dir = None
        self._file_path = None
        self._is_skipped = False
        self._full_pixmap = QPixmap()
        self._zoom_factor = 1.0
        self._fit_to_view = True
        self._init_ui()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Preview area (Scrollable and Zoomable)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)  # We handle resizing ourselves
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: #f0f0f0; border: 1px solid #ccc; }")
        self.scroll_area.setMinimumSize(400, 400)

        self.preview_label = QLabel("No file selected")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self.scroll_area.setWidget(self.preview_label)
        layout.addWidget(self.scroll_area)

        # File info
        info_layout = QVBoxLayout()

        # Original filename
        original_layout = QHBoxLayout()
        original_layout.addWidget(QLabel("Original:"))
        self.original_label = QLabel("-")
        self.original_label.setStyleSheet("QLabel { font-weight: bold; }")
        original_layout.addWidget(self.original_label)
        original_layout.addStretch()
        info_layout.addLayout(original_layout)

        # Suggested filename
        filename_layout = QHBoxLayout()
        filename_layout.addWidget(QLabel("Filename:"))
        self.filename_edit = QLineEdit()
        self.filename_edit.setPlaceholderText("Suggested filename will appear here")
        self.filename_edit.textChanged.connect(self._on_filename_changed)
        filename_layout.addWidget(self.filename_edit)
        info_layout.addLayout(filename_layout)

        # Suggested destination
        dest_layout = QHBoxLayout()
        dest_layout.addWidget(QLabel("Destination:"))
        self.dest_edit = QLineEdit()
        self.dest_edit.setPlaceholderText("Suggested destination will appear here")
        self.dest_edit.textChanged.connect(self._on_destination_changed)
        dest_layout.addWidget(self.dest_edit)

        # Add browse button
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._on_browse_clicked)
        dest_layout.addWidget(self.browse_button)

        info_layout.addLayout(dest_layout)

        # Confidence and reasoning
        self.confidence_label = QLabel("Confidence: -")
        info_layout.addWidget(self.confidence_label)

        self.reasoning_label = QLabel("Reasoning: -")
        self.reasoning_label.setWordWrap(True)
        info_layout.addWidget(self.reasoning_label)

        layout.addLayout(info_layout)

        # Action buttons
        button_layout = QHBoxLayout()

        self.skip_button = QPushButton("Skip This File")
        self.skip_button.setCheckable(True)
        self.skip_button.clicked.connect(self._on_skip_clicked)
        button_layout.addWidget(self.skip_button)

        button_layout.addStretch()

        # Zoom controls
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(30)
        zoom_in_btn.clicked.connect(self.zoom_in)
        button_layout.addWidget(zoom_in_btn)

        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setFixedWidth(30)
        zoom_out_btn.clicked.connect(self.zoom_out)
        button_layout.addWidget(zoom_out_btn)

        self.fit_button = QPushButton("Fit")
        self.fit_button.setFixedWidth(50)
        self.fit_button.clicked.connect(self.reset_zoom)
        button_layout.addWidget(self.fit_button)

        layout.addLayout(button_layout)

    def set_file(self, file_path: str | Path):
        """Set the file to display.

        Args:
            file_path: Path to the file.
        """

        self._file_path = Path(file_path)
        self.original_label.setText(self._file_path.name)

        logger.debug(f"Loading file: {self._file_path}")

        # Try to load preview for images
        if self._file_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}:
            try:
                logger.debug(f"Loading image file with PIL optimization: {self._file_path}")

                # Load and downsize using PIL before converting to QPixmap
                with Image.open(str(self._file_path)) as img:
                    # Target a reasonable preview size (e.g., 2000px)
                    limit = 2000

                    # Use draft mode for JPEGs to reduce memory usage during load
                    if img.format == "JPEG" and (img.width > limit or img.height > limit):
                        img.draft(None, (limit, limit))

                    # If very large, downsize now (thumbnail() is memory efficient)
                    if img.width > limit or img.height > limit:
                        logger.debug(f"Downsizing large image for preview: {img.width}x{img.height}")
                        img.thumbnail((limit, limit), Image.Resampling.LANCZOS)

                    # Convert to QPixmap
                    pixmap = self._pil_to_qpixmap(img)

                if pixmap.isNull():
                    raise ValueError("Failed to create QPixmap from image data")

                self._full_pixmap = pixmap
                self._zoom_factor = 1.0
                self._fit_to_view = True
                self._update_preview()
                logger.debug(f"Successfully loaded image preview: {self._file_path.name}")

            except Exception as e:
                logger.error(f"Image preview loading failed for {self._file_path}: {e}", exc_info=True)
                self.preview_label.setText(f"Could not load image\n{self._file_path.name}\n{str(e)}")
                self._full_pixmap = QPixmap()

        elif self._file_path.suffix.lower() == ".pdf":
            # For PDFs, try multiple approaches
            logger.debug(f"Loading PDF file: {self._file_path}")
            try:
                # Try using pdf2image first (most reliable for rendering)
                try:
                    logger.debug("Attempting PDF rendering with pdf2image")

                    # Convert first page only (use a higher DPI for zooming headroom)
                    images = convert_from_path(
                        str(self._file_path),
                        first_page=1,
                        last_page=1,
                        dpi=200,
                        size=(1200, None)
                    )

                    if images:
                        # Convert PIL Image to QPixmap
                        img = images[0]
                        pixmap = self._pil_to_qpixmap(img)

                        if not pixmap.isNull():
                            self._full_pixmap = pixmap
                            self._zoom_factor = 1.0
                            self._fit_to_view = True
                            self._update_preview()
                            logger.debug(f"Successfully rendered PDF with pdf2image: {self._file_path.name}")
                            return
                        else:
                            logger.warning("pdf2image produced null pixmap")
                    else:
                        logger.warning("pdf2image returned no images")

                except Exception as e:
                    logger.warning(f"pdf2image failed: {e}")

                # Fallback: Try extracting embedded images from PDF
                logger.debug("Attempting PDF image extraction with pypdf")
                pdf_reader = PdfReader(str(self._file_path))

                if len(pdf_reader.pages) > 0:
                    page = pdf_reader.pages[0]
                    images_found = False

                    # Try to extract images from the page
                    try:
                        if '/Resources' in page and '/XObject' in page['/Resources']:
                            x_object = page['/Resources']['/XObject'].get_object()

                            for obj_name in x_object:
                                obj = x_object[obj_name]
                                if obj.get('/Subtype') == '/Image':
                                    try:
                                        logger.debug(f"Extracting image object: {obj_name}")
                                        width = int(obj['/Width'])
                                        height = int(obj['/Height'])
                                        data = obj.get_data()
                                        color_space = obj.get('/ColorSpace', '/DeviceRGB')

                                        if color_space == '/DeviceRGB':
                                            mode = "RGB"
                                        elif color_space == '/DeviceGray':
                                            mode = "L"
                                        elif color_space == '/DeviceCMYK':
                                            mode = "CMYK"
                                        else:
                                            mode = "RGB"

                                        img = Image.frombytes(mode, (width, height), data)
                                        if mode == "CMYK":
                                            img = img.convert("RGB")

                                        pixmap = self._pil_to_qpixmap(img)
                                        if not pixmap.isNull():
                                            self._full_pixmap = pixmap
                                            self._zoom_factor = 1.0
                                            self._fit_to_view = True
                                            self._update_preview()
                                            images_found = True
                                            break
                                    except Exception as e:
                                        logger.warning(f"Fallback image extraction failed for {obj_name}: {e}")
                                        continue

                        if not images_found:
                            self.preview_label.setText(f"PDF loaded but no images found on first page.\n{self._file_path.name}")
                            self._full_pixmap = QPixmap()
                    except Exception as e:
                        logger.warning(f"PDF extraction structure error: {e}")
                        self.preview_label.setText(f"Could not extract content from PDF.\n{str(e)}")
                        self._full_pixmap = QPixmap()
                else:
                    self.preview_label.setText(f"PDF file has no pages.\n{self._file_path.name}")
                    self._full_pixmap = QPixmap()

            except Exception as e:
                logger.error(f"PDF preview failed for {self._file_path}: {e}")
                self.preview_label.setText(f"Could not load PDF preview.\n{str(e)}")
                self._full_pixmap = QPixmap()
        else:
            # For other file types, show placeholder
            logger.debug(f"Unsupported file type: {self._file_path.suffix}")
            self.preview_label.setText(f"File: {self._file_path.name}\n(Preview not available)")
            self._full_pixmap = QPixmap()


    def set_suggestion(
        self,
        filename: str,
        destination: str,
        confidence: float,
        reasoning: str,
    ):
        """Set the filing suggestion.

        Args:
            filename: Suggested filename.
            destination: Suggested destination path.
            confidence: Confidence score (0-1).
            reasoning: Explanation of the suggestion.
        """
        self.filename_edit.setText(filename)
        self.dest_edit.setText(destination)
        self.confidence_label.setText(f"Confidence: {confidence:.1%}")
        self.reasoning_label.setText(f"Reasoning: {reasoning}")

    def clear_suggestion(self):
        """Clear the current filing suggestion."""
        self.filename_edit.clear()
        self.dest_edit.clear()
        self.confidence_label.setText("Confidence: -")
        self.reasoning_label.setText("Reasoning: -")

    def _pil_to_qpixmap(self, img: Image.Image) -> QPixmap:
        """Convert PIL Image to QPixmap.

        Args:
            img: PIL Image object.

        Returns:
            QPixmap object.
        """
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        pixmap = QPixmap()
        pixmap.loadFromData(img_byte_arr.getvalue())
        return pixmap

    def get_filename(self) -> str:
        """Get the current filename.

        Returns:
            Current filename from the edit field.
        """
        return self.filename_edit.text()

    def get_destination(self) -> str:
        """Get the current destination.

        Returns:
            Current destination from the edit field.
        """
        return self.dest_edit.text()

    def is_skipped(self) -> bool:
        """Check if this file is marked to be skipped.

        Returns:
            True if file should be skipped.
        """
        return self._is_skipped

    def reset(self):
        """Reset the viewer to empty state."""
        self._file_path = None
        self._is_skipped = False
        self.preview_label.setText("No file selected")
        self.preview_label.setPixmap(QPixmap())  # Clear pixmap
        self.original_label.setText("-")
        self.filename_edit.clear()
        self.dest_edit.clear()
        self.confidence_label.setText("Confidence: -")
        self.reasoning_label.setText("Reasoning: -")
        self.skip_button.setChecked(False)

    def _on_skip_clicked(self, checked: bool):
        """Handle skip button click."""
        self._is_skipped = checked

        if checked:
            # Disable editing when skipped
            self.filename_edit.setEnabled(False)
            self.dest_edit.setEnabled(False)
            self.dest_edit.clear()  # Clear destination to indicate skip
            self.skip_button.setText("Unskip This File")
        else:
            # Re-enable editing
            self.filename_edit.setEnabled(True)
            self.dest_edit.setEnabled(True)
            self.skip_button.setText("Skip This File")

        self.skip_toggled.emit(checked)

    def _on_browse_clicked(self):
        """Handle browse button click."""
        # Use source_dir as start, or fallback to current dest or home
        start_dir = self.source_dir
        if not start_dir:
            start_dir = Path.home()
        else:
            start_dir = Path(start_dir)

        current_dest = self.dest_edit.text().strip()
        if current_dest:
            potential_path = start_dir / current_dest
            if potential_path.exists():
                start_dir = potential_path

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Destination Folder",
            str(start_dir),
            QFileDialog.Option.ShowDirsOnly,
        )

        if folder:
            folder_path = Path(folder)
            # Try to make relative to source_dir if possible
            if self.source_dir:
                try:
                    rel_path = folder_path.relative_to(Path(self.source_dir))
                    self.dest_edit.setText(str(rel_path))
                    return
                except ValueError:
                    # Not relative to source_dir
                    pass

            # Fallback to full path
            self.dest_edit.setText(str(folder_path))

    def _update_preview(self):
        """Update the preview image based on current zoom and fit settings."""
        if self._full_pixmap.isNull():
            return

        if self._fit_to_view:
            # Calculate zoom factor to fit the scroll area
            area_size = self.scroll_area.viewport().size()
            scaled = self._full_pixmap.scaled(
                area_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            # Update internal zoom factor to match
            self._zoom_factor = scaled.width() / self._full_pixmap.width()
        else:
            # Apply manual zoom factor
            new_size = self._full_pixmap.size() * self._zoom_factor
            scaled = self._full_pixmap.scaled(
                new_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

        self.preview_label.setPixmap(scaled)
        self.preview_label.resize(scaled.size())

    def zoom_in(self):
        """Increase zoom factor."""
        self._fit_to_view = False
        self._zoom_factor *= 1.2
        self._update_preview()

    def zoom_out(self):
        """Decrease zoom factor."""
        self._fit_to_view = False
        self._zoom_factor /= 1.2
        # Minimum zoom 10%
        self._zoom_factor = max(0.1, self._zoom_factor)
        self._update_preview()

    def reset_zoom(self):
        """Reset to Fit to View mode."""
        self._fit_to_view = True
        self._update_preview()

    def resizeEvent(self, event):
        """Handle resize events to update Fit to View."""
        super().resizeEvent(event)
        if self._fit_to_view:
            self._update_preview()

    def wheelEvent(self, event):
        """Handle mouse wheel for zooming with Ctrl."""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
        else:
            super().wheelEvent(event)

    def _on_filename_changed(self, text: str):
        """Handle filename text change."""
        self.filename_changed.emit(text)

    def _on_destination_changed(self, text: str):
        """Handle destination text change."""
        self.destination_changed.emit(text)
