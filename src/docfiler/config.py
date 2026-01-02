"""Configuration management for Document Filer.

This module handles loading and validating configuration from environment variables.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

VLMProvider = Literal["claude", "openai", "gemini"]


@dataclass
class Config:
    """Application configuration."""

    # API Configuration
    vlm_provider: VLMProvider
    anthropic_api_key: str | None
    openai_api_key: str | None
    gemini_api_key: str | None
    vlm_max_tokens: int

    # Model Configuration
    claude_model: str
    openai_model: str
    gemini_model: str

    # Image Processing Configuration
    image_dpi: int
    max_image_dimension: int
    pdf_pages_to_extract: int

    # File Organization
    source_dir: str | None
    default_dest_base: str | None

    # Logging
    log_level: str

    @property
    def active_api_key(self) -> str:
        """Get the API key for the active provider."""
        key_map = {
            "claude": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
        }
        key = key_map.get(self.vlm_provider)
        if not key:
            msg = f"API key not configured for provider: {self.vlm_provider}"
            raise ValueError(msg)
        return key

    @property
    def active_model(self) -> str:
        """Get the model name for the active provider."""
        model_map = {
            "claude": self.claude_model,
            "openai": self.openai_model,
            "gemini": self.gemini_model,
        }
        return model_map[self.vlm_provider]


def load_config(env_path: str | Path | None = None) -> Config:
    """Load configuration from environment variables.

    Args:
        env_path: Path to .env file. If None, searches for .env in current directory.

    Returns:
        Config object with validated settings.

    Raises:
        ValueError: If required configuration is missing or invalid.
    """
    # Load .env file if it exists
    if env_path:
        load_dotenv(env_path)
    else:
        load_dotenv()

    # Load and validate VLM provider
    vlm_provider = os.getenv("VLM_PROVIDER", "claude").lower()
    if vlm_provider not in ("claude", "openai", "gemini"):
        msg = f"Invalid VLM_PROVIDER: {vlm_provider}. Must be 'claude', 'openai', or 'gemini'"
        raise ValueError(msg)

    # Load API keys
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    # Load model configurations
    claude_model = os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

    try:
        vlm_max_tokens = int(os.getenv("VLM_MAX_TOKENS", "1024"))
        if vlm_max_tokens <= 0:
            raise ValueError("VLM_MAX_TOKENS must be positive")
    except ValueError as e:
        msg = f"Invalid VLM_MAX_TOKENS: {e}"
        raise ValueError(msg) from e

    # Load image processing settings
    try:
        image_dpi = int(os.getenv("IMAGE_DPI", "300"))
        if image_dpi <= 0:
            raise ValueError("IMAGE_DPI must be positive")
    except ValueError as e:
        msg = f"Invalid IMAGE_DPI: {e}"
        raise ValueError(msg) from e

    try:
        max_image_dimension = int(os.getenv("MAX_IMAGE_DIMENSION", "2048"))
        if max_image_dimension <= 0:
            raise ValueError("MAX_IMAGE_DIMENSION must be positive")
    except ValueError as e:
        msg = f"Invalid MAX_IMAGE_DIMENSION: {e}"
        raise ValueError(msg) from e

    try:
        pdf_pages_to_extract = int(os.getenv("PDF_PAGES_TO_EXTRACT", "3"))
        if pdf_pages_to_extract <= 0:
            raise ValueError("PDF_PAGES_TO_EXTRACT must be positive")
    except ValueError as e:
        msg = f"Invalid PDF_PAGES_TO_EXTRACT: {e}"
        raise ValueError(msg) from e

    # Load file organization settings
    source_dir = os.getenv("SOURCE_DIR") or None
    default_dest_base = os.getenv("DEFAULT_DEST_BASE") or None

    # Load logging configuration
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    valid_log_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
    if log_level not in valid_log_levels:
        msg = f"Invalid LOG_LEVEL: {log_level}. Must be one of {valid_log_levels}"
        raise ValueError(msg)

    config = Config(
        vlm_provider=vlm_provider,
        anthropic_api_key=anthropic_api_key,
        openai_api_key=openai_api_key,
        gemini_api_key=gemini_api_key,
        vlm_max_tokens=vlm_max_tokens,
        claude_model=claude_model,
        openai_model=openai_model,
        gemini_model=gemini_model,
        image_dpi=image_dpi,
        max_image_dimension=max_image_dimension,
        pdf_pages_to_extract=pdf_pages_to_extract,
        source_dir=source_dir,
        default_dest_base=default_dest_base,
        log_level=log_level,
    )

    # Validate that the selected provider has an API key
    _ = config.active_api_key  # This will raise if key is missing

    return config
