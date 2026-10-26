"""Unit tests for config module."""

import logging
import os
import sys
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from docfiler import config as cfg
from docfiler.config import load_config, model_env_var

from .conftest import make_config


@pytest.fixture
def env():
    """Run load_config against only the given env vars (no .env file)."""

    def _load(**values):
        with patch.dict(os.environ, values, clear=True), patch("docfiler.config.load_dotenv"):
            return load_config()

    return _load


class TestConfig:
    def test_active_api_key(self):
        assert make_config().active_api_key == "test_key"

    def test_active_api_key_missing(self):
        config = make_config(api_keys={"claude": None})
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            _ = config.active_api_key

    @pytest.mark.parametrize("provider", ["claude-cli", "codex-cli"])
    def test_cli_providers_need_no_key(self, provider):
        config = make_config(vlm_provider=provider, api_keys={})
        assert config.active_api_key is None

    def test_active_model(self):
        assert make_config(vlm_provider="openai").active_model == "gpt-4o"
        assert make_config(vlm_provider="claude-cli").active_model == ""

    def test_dest_base_prefers_default_dest_base(self):
        assert make_config(source_dir="/src").dest_base == "/src"
        assert make_config(source_dir="/src", default_dest_base="/dest").dest_base == "/dest"

    def test_with_provider(self):
        config = make_config()
        assert config.with_provider("claude-cli").vlm_provider == "claude-cli"
        assert config.vlm_provider == "claude"  # original unchanged
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            config.with_provider("openai")
        with pytest.raises(ValueError, match="Invalid VLM_PROVIDER"):
            config.with_provider("bogus")

    def test_model_env_var(self):
        assert model_env_var("claude") == "CLAUDE_MODEL"
        assert model_env_var("codex-cli") == "CODEX_CLI_MODEL"


class TestLoadConfig:
    def test_defaults_to_claude_cli_without_keys(self, env):
        config = env()
        assert config.vlm_provider == "claude-cli"
        assert config.vlm_max_tokens == 4096
        assert config.pdf_pages_to_extract == 3

    def test_load_success(self, env):
        config = env(VLM_PROVIDER="claude", ANTHROPIC_API_KEY="k", IMAGE_DPI="200", CODEX_CLI_MODEL="gpt-5")
        assert config.vlm_provider == "claude"
        assert config.active_api_key == "k"
        assert config.image_dpi == 200
        assert config.models["codex-cli"] == "gpt-5"

    def test_missing_key_fails_fast(self, env):
        with pytest.raises(ValueError, match="API key not configured"):
            env(VLM_PROVIDER="openai")

    def test_invalid_provider(self, env):
        with pytest.raises(ValueError, match="Invalid VLM_PROVIDER"):
            env(VLM_PROVIDER="invalid")

    @pytest.mark.parametrize(
        ("value", "match"),
        [("invalid", "Invalid IMAGE_DPI"), ("-100", "IMAGE_DPI must be positive"), ("0", "positive")],
    )
    def test_invalid_int(self, env, value, match):
        with pytest.raises(ValueError, match=match):
            env(IMAGE_DPI=value)

    def test_invalid_log_level(self, env):
        with pytest.raises(ValueError, match="Invalid LOG_LEVEL"):
            env(LOG_LEVEL="INVALID")

    def test_paths_expand_user(self, env):
        config = env(SOURCE_DIR="~/Docs", DEFAULT_DEST_BASE="", INPUT_DIR="")
        assert config.source_dir == str(Path.home() / "Docs")
        assert config.default_dest_base is None
        assert config.input_dir is None

    def test_ignore_patterns(self, env):
        assert env(SCAN_IGNORE_PATTERNS=r" \.git , ,node_modules").scan_ignore_patterns == [r"\.git", "node_modules"]


def test_setup_logging_writes_debug_and_warnings_to_temp_log(monkeypatch):
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    try:
        log_file = cfg.setup_logging("test")
        assert log_file.parent == cfg.LOG_FILE_DIR and log_file.suffix == ".log"
        logging.getLogger("docfiler.x").debug("debug line")
        warnings.warn("a warning", stacklevel=1)
        for h in root.handlers:
            h.flush()
        text = log_file.read_text()
        assert "debug line" in text and "a warning" in text
    finally:
        for h in root.handlers[len(handlers):]:
            h.close()
        root.handlers[:] = handlers
        root.setLevel(level)
        logging.captureWarnings(False)
