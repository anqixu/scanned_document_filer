"""File viewer widget for Document Filer GUI.

This module provides a widget to display and edit document filing information.
"""

import io
import logging
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pdf2image import convert_from_path

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
        self._init_ui()
        self._file_path = None
        self._is_skipped = False

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Preview area (for images/PDFs)
        self.preview_label = QLabel("No file selected")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(400, 400)
        self.preview_label.setStyleSheet("QLabel { background-color: #f0f0f0; border: 1px solid #ccc; }")
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.preview_label)

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
                logger.debug(f"Loading image file: {self._file_path}")
                
                # Try to load with QPixmap first
                pixmap = QPixmap(str(self._file_path))
                
                # If QPixmap fails (e.g., image too large), use PIL to resize first
                if pixmap.isNull():
                    logger.debug(f"QPixmap failed, trying PIL for large image: {self._file_path}")
                    try:
                        # Load with PIL and resize if needed
                        pil_img = Image.open(str(self._file_path))
                        
                        # Get image size
                        width, height = pil_img.size
                        logger.debug(f"Original image size: {width}x{height}")
                        
                        # Resize if too large (max 4000px on longest side)
                        max_size = 4000
                        if width > max_size or height > max_size:
                            logger.debug(f"Resizing large image from {width}x{height}")
                            if width > height:
                                new_width = max_size
                                new_height = int(height * (max_size / width))
                            else:
                                new_height = max_size
                                new_width = int(width * (max_size / height))
                            
                            pil_img = pil_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                            logger.debug(f"Resized to {new_width}x{new_height}")
                        
                        # Convert PIL image to QPixmap
                        img_byte_arr = io.BytesIO()
                        pil_img.save(img_byte_arr, format='PNG')
                        img_byte_arr.seek(0)
                        
                        pixmap = QPixmap()
                        pixmap.loadFromData(img_byte_arr.read())
                        
                        if pixmap.isNull():
                            logger.error(f"Failed to load image even after PIL resize: {self._file_path}")
                            self.preview_label.setText(f"Could not load image\n{self._file_path.name}\n(Image may be corrupted)")
                            return
                    except Exception as e:
                        logger.error(f"PIL image loading failed: {e}", exc_info=True)
                        self.preview_label.setText(f"Could not load image\n{self._file_path.name}\n{str(e)}")
                        return
                
                # Scale to fit preview
                scaled = pixmap.scaled(
                    self.preview_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.preview_label.setPixmap(scaled)
                logger.debug(f"Successfully loaded image: {self._file_path.name}")
                
            except Exception as e:
                logger.error(f"Error loading image {self._file_path}: {e}", exc_info=True)
                self.preview_label.setText(f"Error loading image\n{str(e)}")

        elif self._file_path.suffix.lower() == ".pdf":
            # For PDFs, try multiple approaches
            logger.debug(f"Loading PDF file: {self._file_path}")
            try:
                # Try using pdf2image first (most reliable for rendering)
                try:
                    logger.debug("Attempting PDF rendering with pdf2image")

                    # Convert first page only
                    images = convert_from_path(
                        str(self._file_path),
                        first_page=1,
                        last_page=1,
                        dpi=150,
                        size=(800, None)  # Limit width to 800px
                    )

                    if images:
                        # Convert PIL Image to QPixmap
                        img = images[0]
                        img_byte_arr = io.BytesIO()
                        img.save(img_byte_arr, format='PNG')
                        img_byte_arr.seek(0)

                        pixmap = QPixmap()
                        pixmap.loadFromData(img_byte_arr.read())

                        if not pixmap.isNull():
                            scaled = pixmap.scaled(
                                self.preview_label.size(),
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                            self.preview_label.setPixmap(scaled)
                            logger.debug(f"Successfully rendered PDF with pdf2image: {self._file_path.name}")
                            return
                        else:
                            logger.warning("pdf2image produced null pixmap")
                    else:
                        logger.warning("pdf2image returned no images")

                except ImportError:
                    logger.debug("pdf2image not available, falling back to pypdf")
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

                                        # Get image properties
                                        width = int(obj['/Width'])
                                        height = int(obj['/Height'])
                                        
                                        # Get decompressed data (pypdf handles decompression)
                                        try:
                                            data = obj.get_data()
                                        except Exception as e:
                                            logger.warning(f"Failed to get data for {obj_name}: {e}")
                                            continue

                                        # Determine color mode and expected size
                                        color_space = obj.get('/ColorSpace', '/DeviceRGB')
                                        bits_per_component = int(obj.get('/BitsPerComponent', 8))
                                        
                                        if color_space == '/DeviceRGB':
                                            mode = "RGB"
                                            expected_size = width * height * 3
                                        elif color_space == '/DeviceGray':
                                            mode = "L"
                                            expected_size = width * height
                                        elif color_space == '/DeviceCMYK':
                                            mode = "CMYK"
                                            expected_size = width * height * 4
                                        else:
                                            # Try RGB as default
                                            mode = "RGB"
                                            expected_size = width * height * 3

                                        logger.debug(f"Image properties: {width}x{height}, mode={mode}, bits={bits_per_component}, data_size={len(data)}, expected={expected_size}")
                                        
                                        # Check if we have enough data
                                        if len(data) < expected_size:
                                            logger.warning(f"Not enough image data for {obj_name}: got {len(data)} bytes, expected {expected_size}")
                                            continue

                                        # Create PIL Image
                                        try:
                                            img = Image.frombytes(mode, (width, height), data[:expected_size])
                                            
                                            # Convert CMYK to RGB if needed
                                            if mode == "CMYK":
                                                img = img.convert("RGB")
                                        except Exception as e:
                                            logger.warning(f"Failed to create image from bytes for {obj_name}: {e}")
                                            continue

                                        # Convert to QPixmap
                                        img_byte_arr = io.BytesIO()
                                        img.save(img_byte_arr, format='PNG')
                                        img_byte_arr.seek(0)

                                        pixmap = QPixmap()
                                        pixmap.loadFromData(img_byte_arr.read())

                                        if not pixmap.isNull():
                                            scaled = pixmap.scaled(
                                                self.preview_label.size(),
                                                Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation,
                                            )
                                            self.preview_label.setPixmap(scaled)
                                            images_found = True
                                            logger.debug(f"Successfully extracted image from PDF: {self._file_path.name}")
                                            break
                                        else:
                                            logger.warning("Extracted image produced null pixmap")

                                    except Exception as e:
                                        logger.warning(f"Failed to extract image {obj_name}: {e}")
                                        continue
                    except Exception as e:
                        logger.warning(f"Error accessing PDF XObjects: {e}")

                    if not images_found:
                        # Final fallback: show PDF info
                        page_count = len(pdf_reader.pages)
                        info_text = (
                            f"PDF Document\n{self._file_path.name}\n\n"
                            f"{page_count} page{'s' if page_count != 1 else ''}\n\n"
                            f"(Preview not available)\n\n"
                            f"For PDF previews, install:\n"
                            f"pip install pdf2image\n"
                            f"sudo apt install poppler-utils"
                        )
                        self.preview_label.setText(info_text)
                        logger.info(f"Showing PDF info for: {self._file_path.name} ({page_count} pages) - preview not available")
                else:
                    self.preview_label.setText("Empty PDF")
                    logger.warning(f"PDF has no pages: {self._file_path}")

            except Exception as e:
                error_msg = f"Could not load PDF: {str(e)}"
                logger.error(f"Error loading PDF {self._file_path}: {e}", exc_info=True)
                self.preview_label.setText(f"{error_msg}\n{self._file_path.name}")
        else:
            # For other file types, show placeholder
            logger.debug(f"Unsupported file type: {self._file_path.suffix}")
            self.preview_label.setText(f"File: {self._file_path.name}\n(Preview not available)")


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

    def _on_filename_changed(self, text: str):
        """Handle filename text change."""
        self.filename_changed.emit(text)

    def _on_destination_changed(self, text: str):
        """Handle destination text change."""
        self.destination_changed.emit(text)
