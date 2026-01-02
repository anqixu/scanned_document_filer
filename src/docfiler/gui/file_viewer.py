"""File viewer widget for Document Filer GUI.

This module provides a widget to display and edit document filing information.
"""

from pathlib import Path

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

        # Try to load preview for images
        if self._file_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
            pixmap = QPixmap(str(self._file_path))
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    self.preview_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.preview_label.setPixmap(scaled)
            else:
                self.preview_label.setText("Could not load image")
        else:
            # For PDFs, show placeholder
            self.preview_label.setText(f"PDF Document\n{self._file_path.name}")

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
