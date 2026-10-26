"""Shared fixtures: isolate tests from the real .env, logs/, data/ and cache/."""

import shutil

import pytest

from docfiler import config as cfg
from docfiler.config import DEFAULT_MODELS, Config

REAL_PROMPT = cfg.DATA_DIR / "prompt.md"


def make_config(**overrides) -> Config:
    """Build a Config with test defaults; override any field by keyword."""
    values = {
        "vlm_provider": "claude",
        "api_keys": {"claude": "test_key", "openai": None, "gemini": None},
        "models": dict(DEFAULT_MODELS),
        "vlm_max_tokens": 1024,
        "vlm_max_parallel": 1,
        "image_dpi": 300,
        "max_image_dimension": 2048,
        "pdf_pages_to_extract": 3,
        "source_dir": None,
        "default_dest_base": None,
        "input_dir": None,
        "scan_ignore_patterns": [],
        "log_level": "INFO",
    }
    values.update(overrides)
    return Config(**values)


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Point data/, logs/ and the .log dir at a temp dir (with a copy of the real prompt.md)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(REAL_PROMPT, data_dir / "prompt.md")
    monkeypatch.setattr(cfg, "DATA_DIR", data_dir)
    monkeypatch.setattr(cfg, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(cfg, "LOG_FILE_DIR", tmp_path / "tmplogs")
    return tmp_path
