"""Image processing utilities for Document Filer.

Converts PDFs and images into size-limited PIL images / PNG bytes, used both
for VLM input and for GUI previews.
"""

import io
import logging
from pathlib import Path

from pdf2image import convert_from_path
from PIL import Image
from pypdf import PdfReader

# Support high-resolution scans by raising the decompression bomb limit (~200MP)
Image.MAX_IMAGE_PIXELS = 200_000_000

# Suppress noisy pypdf warnings about trailer issues
logging.getLogger("pypdf").setLevel(logging.ERROR)

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"})
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf"}


def list_documents(folder: str | Path) -> list[Path]:
    """Return supported document files directly in folder, sorted by name (case-insensitive)."""
    folder = Path(folder)
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS]
    return sorted(files, key=lambda p: p.name.lower())


class ImageProcessor:
    """Handles image and PDF processing operations."""

    def __init__(self, target_dpi: int = 300, max_dimension: int = 2048, pages_to_extract: int = 3):
        """Initialize the image processor.

        Args:
            target_dpi: DPI used to render PDF pages.
            max_dimension: Maximum width or height in pixels.
            pages_to_extract: Number of evenly spaced PDF pages to send (always
                includes first and last page).
        """
        self.target_dpi = target_dpi
        self.max_dimension = max_dimension
        self.pages_to_extract = pages_to_extract

    def process_document(self, file_path: str | Path) -> list[bytes]:
        """Convert a PDF or image into a list of PNG images (as bytes).

        Raises:
            FileNotFoundError: If file does not exist.
            ValueError: If file format is unsupported or nothing could be rendered.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return self.process_pdf(file_path)
        if suffix in IMAGE_EXTENSIONS:
            return self.process_image(file_path)
        raise ValueError(f"Unsupported file format: {suffix}")

    def process_pdf(self, pdf_path: str | Path) -> list[bytes]:
        """Render selected PDF pages (first, evenly spaced middle pages, last) to PNG bytes."""
        pdf_path = Path(pdf_path)
        logger.info(f"Processing PDF: {pdf_path}")

        num_pages = len(PdfReader(pdf_path).pages)
        page_indices = self._get_page_indices(num_pages)
        logger.debug(f"Converting pages {page_indices} from {num_pages} total pages")

        images = [self._image_to_bytes(self.render_pdf_page(pdf_path, idx)) for idx in page_indices]
        if not images:
            raise ValueError(f"No images generated from PDF: {pdf_path}")
        return images

    def process_image(self, image_path: str | Path) -> list[bytes]:
        """Load an image file and return it as a single PNG."""
        logger.info(f"Processing image: {image_path}")
        return [self._image_to_bytes(self.load_image(image_path))]

    def load_image(self, image_path: str | Path) -> Image.Image:
        """Load an image file, downsized to max_dimension, in RGB or L mode."""
        with Image.open(image_path) as img:
            # Draft mode lets JPEG decode at reduced size, saving memory
            if img.format == "JPEG" and max(img.size) > self.max_dimension:
                img.draft(None, (self.max_dimension, self.max_dimension))
            # convert() also forces the (lazy) load before the file is closed
            img = img.convert("L" if img.mode in ("1", "L") else "RGB")
        return self._resize_image(img)

    def render_pdf_page(self, pdf_path: str | Path, page_index: int) -> Image.Image:
        """Render one PDF page (0-based) to an RGB image within max_dimension."""
        pages = convert_from_path(
            pdf_path,
            first_page=page_index + 1,
            last_page=page_index + 1,
            dpi=self.target_dpi,
            size=(self.max_dimension, None),  # cap width while rendering to bound memory
        )
        if not pages:
            raise ValueError(f"Could not render page {page_index + 1} of {pdf_path}")
        return self._resize_image(pages[0].convert("RGB"))

    def _get_page_indices(self, num_pages: int) -> list[int]:
        """Pick up to pages_to_extract evenly spaced page indices, including first and last."""
        n = min(self.pages_to_extract, num_pages)
        if n <= 1:
            return [0] if num_pages else []
        # ceil(i * (num_pages - 1) / (n - 1)) keeps the middle page at num_pages // 2 for n=3
        return sorted({-(-i * (num_pages - 1) // (n - 1)) for i in range(n)})

    def _resize_image(self, img: Image.Image) -> Image.Image:
        """Shrink image in place to fit within max_dimension, keeping aspect ratio."""
        if max(img.size) > self.max_dimension:
            logger.debug(f"Downsizing image from {img.width}x{img.height} to max {self.max_dimension}")
            img.thumbnail((self.max_dimension, self.max_dimension), Image.Resampling.LANCZOS)
        return img

    def _image_to_bytes(self, img: Image.Image) -> bytes:
        """Encode a PIL image as PNG bytes."""
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", dpi=(self.target_dpi, self.target_dpi))
        return buffer.getvalue()
