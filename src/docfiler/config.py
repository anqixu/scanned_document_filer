"""Configuration management for Document Filer.

Loads and validates settings from environment variables (.env), and defines
project-wide paths and logging setup.
"""

import dataclasses
import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Project layout (the package is meant to be installed in editable mode)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "src" / "data"
LOGS_DIR = PROJECT_ROOT / "logs"  # per-request prompt/response audit files
LOG_FILE_DIR = Path(tempfile.gettempdir())  # application .log files
CACHE_DIR = PROJECT_ROOT / "cache"

# Providers: API-key based SDK clients, and local CLIs that use their own login
# (e.g. a Claude or ChatGPT subscription) instead of an API key.
API_KEY_ENV = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}
CLI_PROVIDERS = ("claude-cli", "codex-cli")
PROVIDERS = (*CLI_PROVIDERS, *API_KEY_ENV)

# Default model per provider. Empty means "use the CLI's own default model".
DEFAULT_MODELS = {
    "claude": "claude-opus-5-5",
    "openai": "gpt-4o",
    "gemini": "gemini-3.1-pro-preview",
    "claude-cli": "",
    "codex-cli": "",
}

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def model_env_var(provider: str) -> str:
    """Env var holding the model for a provider, e.g. 'claude-cli' -> 'CLAUDE_CLI_MODEL'."""
    return provider.upper().replace("-", "_") + "_MODEL"


@dataclass
class Config:
    """Application configuration."""

    vlm_provider: str
    api_keys: dict[str, str | None]  # provider -> key (API providers only)
    models: dict[str, str]  # provider -> model name ("" = CLI default)
    vlm_max_tokens: int
    vlm_max_parallel: int

    image_dpi: int
    max_image_dimension: int
    pdf_pages_to_extract: int

    source_dir: str | None  # organized document library (context + move target)
    default_dest_base: str | None  # overrides source_dir as the move target
    input_dir: str | None  # inbox folder auto-loaded by the GUI
    scan_ignore_patterns: list[str]

    log_level: str

    @property
    def active_api_key(self) -> str | None:
        """API key for the active provider (None for CLI providers).

        Raises:
            ValueError: If an API provider is selected but its key is missing.
        """
        if self.vlm_provider in CLI_PROVIDERS:
            return None
        key = self.api_keys.get(self.vlm_provider)
        if not key:
            env = API_KEY_ENV[self.vlm_provider]
            raise ValueError(f"API key not configured for provider {self.vlm_provider}: set {env}")
        return key

    @property
    def active_model(self) -> str:
        """Model name for the active provider."""
        return self.models.get(self.vlm_provider, "")

    @property
    def dest_base(self) -> str | None:
        """Base directory that relative destinations are resolved against."""
        return self.default_dest_base or self.source_dir

    def with_provider(self, provider: str) -> "Config":
        """Return a copy using another provider, validating that it is usable."""
        if provider not in PROVIDERS:
            raise ValueError(f"Invalid VLM_PROVIDER: {provider}. Must be one of {PROVIDERS}")
        new = dataclasses.replace(self, vlm_provider=provider)
        _ = new.active_api_key  # raises if the key is missing
        return new


def _positive_int(name: str, default: int) -> int:
    """Read a positive integer env var."""
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    except ValueError as e:
        raise ValueError(f"Invalid {name}: {e}") from e
    return value


def _path_env(name: str, default: str = "") -> str | None:
    """Read a path env var with ~ expanded; empty means unset."""
    raw = os.getenv(name, default).strip()
    return str(Path(raw).expanduser()) if raw else None


def load_config(env_path: str | Path | None = None) -> Config:
    """Load configuration from environment variables.

    Args:
        env_path: Path to .env file. If None, searches upward from this package.

    Returns:
        Config object with validated settings.

    Raises:
        ValueError: If required configuration is missing or invalid.
    """
    load_dotenv(env_path)  # None -> search upward for .env

    provider = os.getenv("VLM_PROVIDER", "claude-cli").strip().lower()
    if provider not in PROVIDERS:
        raise ValueError(f"Invalid VLM_PROVIDER: {provider}. Must be one of {PROVIDERS}")

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    if log_level not in LOG_LEVELS:
        raise ValueError(f"Invalid LOG_LEVEL: {log_level}. Must be one of {LOG_LEVELS}")

    ignore_raw = os.getenv("SCAN_IGNORE_PATTERNS", "")

    config = Config(
        vlm_provider=provider,
        api_keys={p: os.getenv(env) or None for p, env in API_KEY_ENV.items()},
        models={p: os.getenv(model_env_var(p), d).strip() for p, d in DEFAULT_MODELS.items()},
        vlm_max_tokens=_positive_int("VLM_MAX_TOKENS", 4096),
        vlm_max_parallel=_positive_int("VLM_MAX_PARALLEL", 1),
        image_dpi=_positive_int("IMAGE_DPI", 300),
        max_image_dimension=_positive_int("MAX_IMAGE_DIMENSION", 2048),
        pdf_pages_to_extract=_positive_int("PDF_PAGES_TO_EXTRACT", 3),
        source_dir=_path_env("SOURCE_DIR"),
        default_dest_base=_path_env("DEFAULT_DEST_BASE"),
        input_dir=_path_env("INPUT_DIR", "~/GDrive/SHARED/__IN__"),
        scan_ignore_patterns=[p.strip() for p in ignore_raw.split(",") if p.strip()],
        log_level=log_level,
    )

    _ = config.active_api_key  # fail fast if the selected provider has no key
    return config


def setup_logging(prefix: str, console_level: int = logging.INFO) -> Path:
    """Route all logging to <tempdir>/<prefix>_<timestamp>.log (DEBUG) and stderr (console_level).

    Python warnings and uncaught exceptions are routed through logging too.

    Returns:
        Path of the log file.
    """
    LOG_FILE_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_FILE_DIR / f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}.log"
    formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for handler in (file_handler, console_handler):
        handler.setFormatter(formatter)
        root.addHandler(handler)

    logging.captureWarnings(True)
    sys.excepthook = _log_uncaught_exception
    return log_file


def _log_uncaught_exception(exc_type, exc, tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc, tb)
        return
    logging.getLogger("docfiler").critical("Uncaught exception", exc_info=(exc_type, exc, tb))
