"""Unit tests for VLM service module."""

from unittest.mock import Mock, patch

from PIL import Image

from docfiler.config import Config
from docfiler.vlm_service import FilingSuggestion, VLMService


class TestFilingSuggestion:
    """Tests for FilingSuggestion dataclass."""

    def test_string_representation(self):
        """Test string representation of suggestion."""
        suggestion = FilingSuggestion(
            filename="2024-01-01_test.pdf",
            destination="docs/bills",
            confidence=0.95,
            reasoning="Test reasoning",
        )

        assert str(suggestion) == "docs/bills/2024-01-01_test.pdf"


class TestVLMService:
    """Tests for VLM service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = Config(
            vlm_provider="claude",
            anthropic_api_key="test_key",
            openai_api_key=None,
            gemini_api_key=None,
            claude_model="claude-3-5-sonnet-20241022",
            openai_model="gpt-4o",
            gemini_model="gemini-2.0-flash-exp",
            image_dpi=300,
            max_image_dimension=2048,
            pdf_pages_to_extract=3,
            vlm_max_tokens=1024,
            source_dir=None,
            scan_ignore_patterns=[],
            default_dest_base=None,
            log_level="INFO",
        )

    @patch("docfiler.vlm_service.Path.exists")
    def test_get_default_context(self, mock_exists):
        """Test default context generation."""
        mock_exists.return_value = False  # Force fallback
        service = VLMService(self.config)
        context = service._get_default_context()

        assert "finances" in context.lower()
        assert "medical" in context.lower()
        assert isinstance(context, str)

    def test_build_prompt(self):
        """Test prompt building with context."""
        context = "Test context about filing"
        service = VLMService(self.config, context=context)

        prompt = service._build_prompt()

        assert "Test context about filing" in prompt

    @patch("docfiler.vlm_service.create_client")
    @patch("docfiler.vlm_service.ImageProcessor")
    def test_analyze_document(self, mock_image_processor_class, mock_create_client, tmp_path):
        """Test document analysis workflow."""
        # Create test image
        img = Image.new("RGB", (100, 100), color="blue")
        test_file = tmp_path / "test.png"
        img.save(test_file)

        # Mock image processor
        mock_processor = Mock()
        mock_processor.process_document.return_value = [b"fake_image_bytes"]
        mock_image_processor_class.return_value = mock_processor

        # Mock API client
        mock_client = Mock()
        mock_client.analyze_document.return_value = {
            "filename": "2024-01-01_test.pdf",
            "destination": "finances/bills",
            "confidence": 0.95,
            "reasoning": "This is a utility bill",
        }
        mock_create_client.return_value = mock_client

        # Test
        service = VLMService(self.config)
        suggestion = service.analyze_document(test_file)

        assert isinstance(suggestion, FilingSuggestion)
        assert suggestion.filename == "2024-01-01_test.pdf"
        assert suggestion.destination == "finances/bills"
        assert suggestion.confidence == 0.95
        assert "utility bill" in suggestion.reasoning

        # Verify calls
        mock_processor.process_document.assert_called_once_with(test_file)
        mock_client.analyze_document.assert_called_once()

    @patch("docfiler.vlm_service.create_client")
    @patch("docfiler.vlm_service.ImageProcessor")
    def test_analyze_document_with_defaults(
        self, mock_image_processor_class, mock_create_client, tmp_path
    ):
        """Test document analysis with missing fields in response."""
        # Create test image
        test_file = tmp_path / "test.jpg"
        img = Image.new("RGB", (100, 100))
        img.save(test_file)

        # Mock processor
        mock_processor = Mock()
        mock_processor.process_document.return_value = [b"bytes"]
        mock_image_processor_class.return_value = mock_processor

        # Mock client with incomplete response
        mock_client = Mock()
        mock_client.analyze_document.return_value = {}  # Missing all fields
        mock_create_client.return_value = mock_client

        # Test
        service = VLMService(self.config)
        suggestion = service.analyze_document(test_file)

        # Should have defaults
        assert suggestion.filename == "untitled.pdf"
        assert suggestion.destination == "unsorted"
        assert suggestion.confidence == 0.0
        assert suggestion.reasoning == "No reasoning provided"


class TestVLMServiceIntegration:
    """Integration tests for VLM service."""

    @patch("docfiler.vlm_service.Path.exists")
    @patch("builtins.open")
    def test_load_prompt_template(self, mock_open, mock_exists):
        """Test loading prompt template from file."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__.return_value.read.return_value = (
            "Custom prompt with {context}"
        )

        config = Config(
            vlm_provider="claude",
            anthropic_api_key="test",
            openai_api_key=None,
            gemini_api_key=None,
            claude_model="test",
            openai_model="test",
            gemini_model="test",
            image_dpi=300,
            max_image_dimension=2048,
            pdf_pages_to_extract=3,
            vlm_max_tokens=1024,
            source_dir=None,
            scan_ignore_patterns=[],
            default_dest_base=None,
            log_level="INFO",
        )

        service = VLMService(config)

        assert "{context}" in service.prompt_template
