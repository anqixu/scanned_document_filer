"""Image processing utilities for Document Filer.

This module handles PDF to image conversion and image optimization.
"""

import io
import logging
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Handles image and PDF processing operations."""

    def __init__(self, target_dpi: int = 300, max_dimension: int = 2048):
        """Initialize the image processor.

        Args:
            target_dpi: Target DPI for image conversion.
            max_dimension: Maximum width or height in pixels.
        """
        self.target_dpi = target_dpi
        self.max_dimension = max_dimension

    def process_document(self, file_path: str | Path) -> list[bytes]:
        """Process a document file and return image data.

        Args:
            file_path: Path to the document file (PDF or image).

        Returns:
            List of image data as bytes (PNG format).

        Raises:
            ValueError: If file format is unsupported.
            FileNotFoundError: If file does not exist.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            return self.process_pdf(file_path)
        elif suffix in {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}:
            return self.process_image(file_path)
        else:
            msg = f"Unsupported file format: {suffix}"
            raise ValueError(msg)

    def process_pdf(self, pdf_path: str | Path) -> list[bytes]:
        """Extract and process pages from a PDF.

        Extracts first, middle, and last pages and converts them to images.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            List of image data as bytes (PNG format).
        """
        pdf_path = Path(pdf_path)
        logger.info(f"Processing PDF: {pdf_path}")

        reader = PdfReader(pdf_path)
        num_pages = len(reader.pages)

        # Determine which pages to extract
        page_indices = self._get_page_indices(num_pages)
        logger.debug(f"Extracting pages {page_indices} from {num_pages} total pages")

        images = []
        for page_idx in page_indices:
            page = reader.pages[page_idx]

            # Extract images from the page
            # Note: This is a simplified approach. For better quality,
            # consider using pdf2image library with poppler
            if "/XObject" in page["/Resources"]:
                x_objects = page["/Resources"]["/XObject"].get_object()

                for obj_name in x_objects:
                    obj = x_objects[obj_name]

                    if obj["/Subtype"] == "/Image":
                        # Extract image data
                        image_data = obj.get_data()
                        width = obj["/Width"]
                        height = obj["/Height"]

                        # Handle different color spaces
                        if "/ColorSpace" in obj:
                            color_space = obj["/ColorSpace"]
                            if color_space == "/DeviceRGB":
                                mode = "RGB"
                            elif color_space == "/DeviceGray":
                                mode = "L"
                            else:
                                mode = "RGB"
                        else:
                            mode = "RGB"

                        try:
                            img = Image.frombytes(mode, (width, height), image_data)
                            processed = self._resize_image(img)
                            img_bytes = self._image_to_bytes(processed)
                            images.append(img_bytes)
                            break  # Take first image from page
                        except Exception as e:
                            logger.warning(f"Failed to extract image from page {page_idx}: {e}")

        # If no images were extracted, create a placeholder
        if not images:
            logger.warning(f"No images extracted from PDF: {pdf_path}")
            # Create a simple placeholder image
            placeholder = Image.new("RGB", (100, 100), color="white")
            images.append(self._image_to_bytes(placeholder))

        return images

    def process_image(self, image_path: str | Path) -> list[bytes]:
        """Process a single image file.

        Args:
            image_path: Path to the image file.

        Returns:
            List containing single processed image as bytes.
        """
        image_path = Path(image_path)
        logger.info(f"Processing image: {image_path}")

        img = Image.open(image_path)

        # Convert to RGB if necessary
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        processed = self._resize_image(img)
        img_bytes = self._image_to_bytes(processed)

        return [img_bytes]

    def _get_page_indices(self, num_pages: int) -> list[int]:
        """Determine which page indices to extract from a PDF.

        Args:
            num_pages: Total number of pages in the PDF.

        Returns:
            List of page indices (0-based).
        """
        if num_pages == 1:
            return [0]
        elif num_pages == 2:
            return [0, 1]
        elif num_pages == 3:
            return [0, 1, 2]
        else:
            # First, middle, last
            middle = num_pages // 2
            return [0, middle, num_pages - 1]

    def _resize_image(self, img: Image.Image) -> Image.Image:
        """Resize image to fit within max_dimension while maintaining aspect ratio.

        Args:
            img: PIL Image object.

        Returns:
            Resized PIL Image object.
        """
        width, height = img.size

        # Calculate scaling factor
        if width > height:
            if width > self.max_dimension:
                scale = self.max_dimension / width
                new_width = self.max_dimension
                new_height = int(height * scale)
            else:
                return img
        else:
            if height > self.max_dimension:
                scale = self.max_dimension / height
                new_height = self.max_dimension
                new_width = int(width * scale)
            else:
                return img

        logger.debug(f"Resizing image from {width}x{height} to {new_width}x{new_height}")
        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def _image_to_bytes(self, img: Image.Image) -> bytes:
        """Convert PIL Image to bytes in PNG format.

        Args:
            img: PIL Image object.

        Returns:
            Image data as bytes.
        """
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", dpi=(self.target_dpi, self.target_dpi))
        return buffer.getvalue()
