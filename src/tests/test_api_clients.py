"""Unit tests for API client module."""

import json
from unittest.mock import MagicMock, Mock, patch

import pytest

from docfiler.api_clients import ClaudeClient, GeminiClient, OpenAIClient, create_client


class TestClaudeClient:
    """Tests for Claude API client."""

    def test_parse_json_response_plain(self):
        """Test parsing plain JSON response."""
        client = ClaudeClient("test_key", "test_model")
        response = '{"filename": "test.pdf", "destination": "docs"}'

        result = client._parse_json_response(response)

        assert result["filename"] == "test.pdf"
        assert result["destination"] == "docs"

    def test_parse_json_response_with_markdown(self):
        """Test parsing JSON in markdown code block."""
        client = ClaudeClient("test_key", "test_model")
        response = """```json
{
  "filename": "2024-01-01_test.pdf",
  "destination": "finances/bills"
}
```"""

        result = client._parse_json_response(response)

        assert result["filename"] == "2024-01-01_test.pdf"
        assert result["destination"] == "finances/bills"

    def test_parse_json_response_invalid(self):
        """Test error on invalid JSON."""
        client = ClaudeClient("test_key", "test_model")
        response = "This is not JSON"

        with pytest.raises(ValueError, match="Invalid JSON response"):
            client._parse_json_response(response)

    @patch("docfiler.api_clients.anthropic.Anthropic")
    def test_analyze_document(self, mock_anthropic):
        """Test document analysis with Claude."""
        # Setup mock
        mock_client = Mock()
        mock_anthropic.return_value = mock_client

        mock_response = Mock()
        mock_response.content = [
            Mock(
                text=json.dumps({
                    "filename": "2024-01-01_test.pdf",
                    "destination": "docs",
                    "confidence": 0.95,
                    "reasoning": "Test",
                })
            )
        ]
        mock_client.messages.create.return_value = mock_response

        # Test
        client = ClaudeClient("test_key", "claude-3-5-sonnet-20241022")
        result = client.analyze_document("Test prompt", [b"fake_image_data"])

        assert result["filename"] == "2024-01-01_test.pdf"
        assert result["destination"] == "docs"
        assert mock_client.messages.create.called


class TestOpenAIClient:
    """Tests for OpenAI API client."""

    @patch("docfiler.api_clients.OpenAI")
    def test_analyze_document(self, mock_openai):
        """Test document analysis with OpenAI."""
        # Setup mock
        mock_client = Mock()
        mock_openai.return_value = mock_client

        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content=json.dumps({
                        "filename": "test.pdf",
                        "destination": "files",
                        "confidence": 0.9,
                        "reasoning": "OpenAI test",
                    })
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response

        # Test
        client = OpenAIClient("test_key", "gpt-4o")
        result = client.analyze_document("Test prompt", [b"image_data"])

        assert result["filename"] == "test.pdf"
        assert result["destination"] == "files"
        assert mock_client.chat.completions.create.called


class TestGeminiClient:
    """Tests for Gemini API client."""

    @patch("docfiler.api_clients.genai")
    def test_analyze_document(self, mock_genai):
        """Test document analysis with Gemini."""
        # Setup mock
        mock_model = Mock()
        mock_genai.GenerativeModel.return_value = mock_model

        mock_response = Mock()
        mock_response.text = json.dumps({
            "filename": "gemini_test.pdf",
            "destination": "test_dir",
            "confidence": 0.85,
            "reasoning": "Gemini reasoning",
        })
        mock_model.generate_content.return_value = mock_response

        # Test
        client = GeminiClient("test_key", "gemini-2.0-flash-exp")
        result = client.analyze_document("Test prompt", [b"image"])

        assert result["filename"] == "gemini_test.pdf"
        assert result["destination"] == "test_dir"
        assert mock_model.generate_content.called


class TestCreateClient:
    """Tests for client factory function."""

    def test_create_claude_client(self):
        """Test creating Claude client."""
        client = create_client("claude", "test_key", "claude-3-5-sonnet-20241022")
        assert isinstance(client, ClaudeClient)

    def test_create_openai_client(self):
        """Test creating OpenAI client."""
        client = create_client("openai", "test_key", "gpt-4o")
        assert isinstance(client, OpenAIClient)

    def test_create_gemini_client(self):
        """Test creating Gemini client."""
        client = create_client("gemini", "test_key", "gemini-2.0-flash-exp")
        assert isinstance(client, GeminiClient)

    def test_create_invalid_provider(self):
        """Test error with invalid provider."""
        with pytest.raises(ValueError, match="Unsupported provider"):
            create_client("invalid", "test_key", "model")
