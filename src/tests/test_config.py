"""Unit tests for config module."""

import os
from unittest.mock import patch

import pytest

from docfiler.config import Config, load_config


class TestConfig:
    """Tests for Config dataclass."""

    def test_active_api_key_claude(self):
        """Test getting active API key for Claude."""
        config = Config(
            vlm_provider="claude",
            anthropic_api_key="test_claude_key",
            openai_api_key=None,
            gemini_api_key=None,
            claude_model="claude-3-5-sonnet-20241022",
            openai_model="gpt-4o",
            gemini_model="gemini-2.0-flash-exp",
            image_dpi=300,
            max_image_dimension=2048,
            pdf_pages_to_extract=3,
            default_dest_base=None,
            log_level="INFO",
        )

        assert config.active_api_key == "test_claude_key"

    def test_active_api_key_missing(self):
        """Test error when API key is missing for active provider."""
        config = Config(
            vlm_provider="claude",
            anthropic_api_key=None,
            openai_api_key=None,
            gemini_api_key=None,
            claude_model="claude-3-5-sonnet-20241022",
            openai_model="gpt-4o",
            gemini_model="gemini-2.0-flash-exp",
            image_dpi=300,
            max_image_dimension=2048,
            pdf_pages_to_extract=3,
            default_dest_base=None,
            log_level="INFO",
        )

        with pytest.raises(ValueError, match="API key not configured"):
            _ = config.active_api_key

    def test_active_model(self):
        """Test getting active model name."""
        config = Config(
            vlm_provider="openai",
            anthropic_api_key=None,
            openai_api_key="test_key",
            gemini_api_key=None,
            claude_model="claude-3-5-sonnet-20241022",
            openai_model="gpt-4o",
            gemini_model="gemini-2.0-flash-exp",
            image_dpi=300,
            max_image_dimension=2048,
            pdf_pages_to_extract=3,
            default_dest_base=None,
            log_level="INFO",
        )

        assert config.active_model == "gpt-4o"


class TestLoadConfig:
    """Tests for load_config function."""

    @patch.dict(
        os.environ,
        {
            "VLM_PROVIDER": "claude",
            "ANTHROPIC_API_KEY": "test_key",
            "IMAGE_DPI": "300",
            "MAX_IMAGE_DIMENSION": "2048",
            "PDF_PAGES_TO_EXTRACT": "3",
            "LOG_LEVEL": "INFO",
        },
    )
    def test_load_config_success(self):
        """Test successful config loading."""
        config = load_config()

        assert config.vlm_provider == "claude"
        assert config.anthropic_api_key == "test_key"
        assert config.image_dpi == 300
        assert config.max_image_dimension == 2048
        assert config.pdf_pages_to_extract == 3
        assert config.log_level == "INFO"

    @patch.dict(os.environ, {"VLM_PROVIDER": "invalid"})
    def test_load_config_invalid_provider(self):
        """Test error with invalid provider."""
        with pytest.raises(ValueError, match="Invalid VLM_PROVIDER"):
            load_config()

    @patch.dict(
        os.environ,
        {
            "VLM_PROVIDER": "claude",
            "ANTHROPIC_API_KEY": "test_key",
            "IMAGE_DPI": "invalid",
        },
    )
    def test_load_config_invalid_dpi(self):
        """Test error with invalid DPI."""
        with pytest.raises(ValueError, match="Invalid IMAGE_DPI"):
            load_config()

    @patch.dict(
        os.environ,
        {
            "VLM_PROVIDER": "claude",
            "ANTHROPIC_API_KEY": "test_key",
            "LOG_LEVEL": "INVALID",
        },
    )
    def test_load_config_invalid_log_level(self):
        """Test error with invalid log level."""
        with pytest.raises(ValueError, match="Invalid LOG_LEVEL"):
            load_config()

    @patch.dict(
        os.environ,
        {
            "VLM_PROVIDER": "claude",
            "ANTHROPIC_API_KEY": "test_key",
            "IMAGE_DPI": "-100",
        },
    )
    def test_load_config_negative_dpi(self):
        """Test error with negative DPI."""
        with pytest.raises(ValueError, match="IMAGE_DPI must be positive"):
            load_config()
