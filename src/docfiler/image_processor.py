"""Image processing utilities for Document Filer.

This module handles PDF to image conversion and image optimization.
"""

import io
import logging
from pathlib import Path

from PIL import Image
from pdf2image import convert_from_path
from pypdf import PdfReader

# Support high-resolution scans by increasing the decompression bomb limit (approx 200MP)
Image.MAX_IMAGE_PIXELS = 200_000_000

# Suppress noisy pypdf warnings about trailer issues
logging.getLogger("pypdf").setLevel(logging.ERROR)

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
        """Convert PDF pages to images using pdf2image.

        Extracts first, middle, and last pages for context.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            List of image data as bytes (PNG format).
        """
        pdf_path = Path(pdf_path)
        logger.info(f"Processing PDF: {pdf_path}")

        try:
            # Get page count using pypdf (lightweight)
            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)
            
            # Determine which pages to extract
            page_indices = self._get_page_indices(num_pages)
            logger.debug(f"Converting pages {page_indices} from {num_pages} total pages")

            images = []
            for idx in page_indices:
                # Convert specific page (1-indexed for pdf2image)
                page_images = convert_from_path(
                    pdf_path,
                    first_page=idx + 1,
                    last_page=idx + 1,
                    dpi=self.target_dpi,
                    size=(self.max_dimension, None) if self.max_dimension else None
                )
                
                if page_images:
                    img = page_images[0]
                    # Ensure RGB
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    
                    # Ensure max_dimension is strictly honored
                    img = self._resize_image(img)
                    images.append(self._image_to_bytes(img))

            if not images:
                raise ValueError("No images generated from PDF")

            return images

        except Exception as e:
            logger.error(f"Failed to process PDF {pdf_path}: {e}")
            # Fallback to a single blank page with error message if needed, 
            # but better to let it propagate or return empty list
            raise

    def process_image(self, image_path: str | Path) -> list[bytes]:
        """Process a single image file.

        Args:
            image_path: Path to the image file.

        Returns:
            List containing single processed image as bytes.
        """
        image_path = Path(image_path)
        logger.info(f"Processing image: {image_path}")

        # Open image lazily
        img = Image.open(image_path)
        
        # Use draft mode for JPEGs to downsize during load if possible
        if img.format == "JPEG" and (img.width > self.max_dimension or img.height > self.max_dimension):
            img.draft(None, (self.max_dimension, self.max_dimension))

        # Convert to RGB if necessary
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        processed = self._resize_image(img)
        img_bytes = self._image_to_bytes(processed)

        # Close image to free resources
        if hasattr(img, "close"):
            img.close()

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

        if width > self.max_dimension or height > self.max_dimension:
            logger.debug(f"Downsizing image from {width}x{height} to max {self.max_dimension}")
            # thumbnail() is more memory efficient than resize()
            img.thumbnail((self.max_dimension, self.max_dimension), Image.Resampling.LANCZOS)
        
        return img

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
