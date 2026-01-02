"""Unit tests for image processor module."""

import io
from pathlib import Path

import pytest
from PIL import Image

from docfiler.image_processor import ImageProcessor


class TestImageProcessor:
    """Tests for ImageProcessor class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.processor = ImageProcessor(target_dpi=300, max_dimension=2048)

    def test_get_page_indices_single_page(self):
        """Test page index calculation for single page PDF."""
        indices = self.processor._get_page_indices(1)
        assert indices == [0]

    def test_get_page_indices_two_pages(self):
        """Test page index calculation for two page PDF."""
        indices = self.processor._get_page_indices(2)
        assert indices == [0, 1]

    def test_get_page_indices_three_pages(self):
        """Test page index calculation for three page PDF."""
        indices = self.processor._get_page_indices(3)
        assert indices == [0, 1, 2]

    def test_get_page_indices_many_pages(self):
        """Test page index calculation for multi-page PDF."""
        indices = self.processor._get_page_indices(10)
        assert indices == [0, 5, 9]  # first, middle, last

    def test_resize_image_no_resize_needed(self):
        """Test that small images are not resized."""
        img = Image.new("RGB", (100, 100), color="red")
        resized = self.processor._resize_image(img)

        assert resized.size == (100, 100)

    def test_resize_image_width_larger(self):
        """Test resizing when width exceeds max dimension."""
        img = Image.new("RGB", (3000, 2000), color="blue")
        resized = self.processor._resize_image(img)

        assert resized.width == 2048
        assert resized.height < 2048  # Maintains aspect ratio

    def test_resize_image_height_larger(self):
        """Test resizing when height exceeds max dimension."""
        img = Image.new("RGB", (2000, 3000), color="green")
        resized = self.processor._resize_image(img)

        assert resized.height == 2048
        assert resized.width < 2048  # Maintains aspect ratio

    def test_image_to_bytes(self):
        """Test converting image to bytes."""
        img = Image.new("RGB", (100, 100), color="yellow")
        img_bytes = self.processor._image_to_bytes(img)

        assert isinstance(img_bytes, bytes)
        assert len(img_bytes) > 0

        # Verify it's a valid PNG
        loaded = Image.open(io.BytesIO(img_bytes))
        assert loaded.format == "PNG"
        assert loaded.size == (100, 100)

    def test_process_image_nonexistent(self):
        """Test processing non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            self.processor.process_document("/nonexistent/file.png")

    def test_process_document_unsupported_format(self, tmp_path):
        """Test processing unsupported file format raises error."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello")

        with pytest.raises(ValueError, match="Unsupported file format"):
            self.processor.process_document(test_file)

    def test_process_image(self, tmp_path):
        """Test processing a simple image file."""
        # Create a test image
        img = Image.new("RGB", (200, 200), color="purple")
        test_file = tmp_path / "test.png"
        img.save(test_file)

        # Process it
        result = self.processor.process_image(test_file)

        assert len(result) == 1
        assert isinstance(result[0], bytes)

        # Verify the output
        output_img = Image.open(io.BytesIO(result[0]))
        assert output_img.size == (200, 200)


class TestImageProcessorIntegration:
    """Integration tests for image processor."""

    def test_process_png_image(self, tmp_path):
        """Test end-to-end processing of PNG image."""
        # Create test image
        img = Image.new("RGB", (400, 300), color="cyan")
        test_file = tmp_path / "test.png"
        img.save(test_file)

        # Process
        processor = ImageProcessor()
        result = processor.process_document(test_file)

        assert len(result) == 1
        assert isinstance(result[0], bytes)

    def test_process_large_image(self, tmp_path):
        """Test processing image that needs resizing."""
        # Create large image
        img = Image.new("RGB", (4000, 3000), color="magenta")
        test_file = tmp_path / "large.jpg"
        img.save(test_file)

        # Process with small max dimension
        processor = ImageProcessor(max_dimension=1000)
        result = processor.process_document(test_file)

        # Verify it was resized
        output_img = Image.open(io.BytesIO(result[0]))
        assert max(output_img.size) <= 1000
