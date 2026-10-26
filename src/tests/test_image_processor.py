"""Unit tests for image processor module."""

import io
import shutil

import pytest
from PIL import Image

from docfiler.image_processor import ImageProcessor, list_documents


def _png(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


class TestPageIndices:
    @pytest.mark.parametrize(
        ("num_pages", "n", "expected"),
        [
            (0, 3, []),
            (1, 3, [0]),
            (2, 3, [0, 1]),
            (3, 3, [0, 1, 2]),
            (4, 3, [0, 2, 3]),
            (10, 3, [0, 5, 9]),  # first, middle, last
            (10, 1, [0]),
            (10, 4, [0, 3, 6, 9]),
            (10, 20, list(range(10))),
        ],
    )
    def test_indices(self, num_pages, n, expected):
        assert ImageProcessor(pages_to_extract=n)._get_page_indices(num_pages) == expected


class TestImageProcessor:
    def setup_method(self):
        self.processor = ImageProcessor(target_dpi=300, max_dimension=2048)

    @pytest.mark.parametrize(("size", "expected_max"), [((100, 100), 100), ((3000, 2000), 2048), ((2000, 3000), 2048)])
    def test_resize(self, size, expected_max):
        resized = self.processor._resize_image(Image.new("RGB", size))
        assert max(resized.size) == expected_max
        assert resized.width / resized.height == pytest.approx(size[0] / size[1], rel=0.01)

    def test_image_to_bytes_is_png(self):
        img = _png(self.processor._image_to_bytes(Image.new("RGB", (100, 100))))
        assert img.format == "PNG" and img.size == (100, 100)

    def test_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            self.processor.process_document("/nonexistent/file.png")

    def test_unsupported_format(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")
        with pytest.raises(ValueError, match="Unsupported file format"):
            self.processor.process_document(test_file)

    @pytest.mark.parametrize(("name", "mode"), [("a.PNG", "RGBA"), ("b.jpg", "RGB"), ("c.tif", "1"), ("d.bmp", "L"), ("e.gif.png", "P")])
    def test_process_image_modes_and_case(self, tmp_path, name, mode):
        path = tmp_path / name
        Image.new(mode, (200, 100)).save(path)
        [data] = self.processor.process_document(path)
        img = _png(data)
        assert img.size == (200, 100) and img.mode in ("RGB", "L")

    def test_process_large_jpeg(self, tmp_path):
        path = tmp_path / "large.jpg"
        Image.new("RGB", (4000, 3000), "magenta").save(path)
        [data] = ImageProcessor(max_dimension=1000).process_document(path)
        assert max(_png(data).size) == 1000

    @pytest.mark.skipif(not shutil.which("pdftoppm"), reason="poppler not installed")
    def test_process_pdf_pages(self, tmp_path):
        path = tmp_path / "doc.PDF"
        pages = [Image.new("RGB", (850, 1100), c) for c in ("red", "green", "blue", "white", "black")]
        pages[0].save(path, save_all=True, append_images=pages[1:])
        images = ImageProcessor(target_dpi=50, max_dimension=400).process_document(path)
        assert len(images) == 3
        assert all(max(_png(d).size) <= 400 for d in images)


def test_list_documents_case_insensitive_and_sorted(tmp_path):
    for name in ("b.PDF", "A.jpg", "c.TIFF", "notes.txt", "d.Png"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "sub.pdf").mkdir()  # directories are ignored
    assert [p.name for p in list_documents(tmp_path)] == ["A.jpg", "b.PDF", "c.TIFF", "d.Png"]
