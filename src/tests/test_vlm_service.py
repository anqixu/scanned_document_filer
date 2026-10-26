"""Unit tests for VLM service module."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from docfiler import config as cfg
from docfiler.cache_manager import CacheManager
from docfiler.models import FilingSuggestion
from docfiler.vlm_service import DEFAULT_CONTEXT, VLMService, make_suggestion, normalize_filename

from .conftest import make_config

RESPONSE = {"filename": "20240101 Bill.pdf", "destination": "Finances/Bills", "confidence": 0.95, "reasoning": "A bill"}


def test_suggestion_str():
    assert str(FilingSuggestion("a.pdf", "docs/bills", 0.9, "r")) == "docs/bills/a.pdf"


class TestNormalizeFilename:
    @pytest.mark.parametrize(
        ("suggested", "original", "expected"),
        [
            ("20240101 Bill.pdf", "scan.pdf", "20240101 Bill.pdf"),
            ("20240101 Bill.PDF", "scan.pdf", "20240101 Bill.pdf"),
            ("20240101 Bill", "scan.pdf", "20240101 Bill.pdf"),
            ("20240101 Bill.pdf", "scan.jpg", "20240101 Bill.jpg"),  # wrong extension replaced
            ("Invoice No. 5", "scan.pdf", "Invoice No. 5.pdf"),  # a dot is not an extension
            ("Personal/Bills/x.pdf", "scan.pdf", "Personal-Bills-x.pdf"),  # no path traversal
            ("", "scan.pdf", "scan.pdf"),
            ("..", "scan.pdf", "scan.pdf"),
        ],
    )
    def test_cases(self, suggested, original, expected):
        assert normalize_filename(suggested, Path(original)) == expected


def test_make_suggestion_defaults_and_coercion():
    s = make_suggestion({"confidence": "high", "destination": "/Finances/"}, Path("x.png"))
    assert s == FilingSuggestion("x.png", "Finances", 0.0, "No reasoning provided")
    assert make_suggestion({"confidence": "0.5"}, Path("x.png")).confidence == 0.5


@pytest.fixture
def service_factory():
    """Build a VLMService with mocked image processing and client."""

    def _make(response=RESPONSE, cache_manager=None, **kwargs):
        with patch("docfiler.vlm_service.create_client_from_config") as create, patch(
            "docfiler.vlm_service.ImageProcessor"
        ) as processor_cls:
            create.return_value.analyze_document.return_value = response
            processor_cls.return_value.process_document.return_value = [b"img"]
            service = VLMService(make_config(), cache_manager=cache_manager, **kwargs)
        return service

    return _make


class TestVLMService:
    def test_default_context_without_context_md(self, service_factory):
        assert service_factory().context == DEFAULT_CONTEXT

    def test_context_md_is_loaded(self, service_factory):
        (cfg.DATA_DIR / "context.md").write_text("My conventions")
        assert service_factory().context == "My conventions"

    def test_build_prompt(self, service_factory):
        (cfg.DATA_DIR / "extra_instructions.md").write_text("Use YYYYMMDD")
        prompt = service_factory(context="Test context")._build_prompt()
        assert "Test context" in prompt and "Use YYYYMMDD" in prompt
        assert "{context}" not in prompt and "{extra_instructions}" not in prompt

    def test_missing_prompt_template_fails_fast(self, service_factory):
        (cfg.DATA_DIR / "prompt.md").unlink()
        with pytest.raises(FileNotFoundError, match="Prompt template"):
            service_factory()

    def test_analyze_document_logs_prompt(self, service_factory, tmp_path):
        test_file = tmp_path / "scan.png"
        Image.new("RGB", (10, 10)).save(test_file)

        suggestion = service_factory().analyze_document(test_file)

        assert suggestion == FilingSuggestion("20240101 Bill.png", "Finances/Bills", 0.95, "A bill")
        [log] = list(cfg.LOGS_DIR.glob("prompt_*_scan.png.md"))
        text = log.read_text()
        assert "## Prompt" in text and "## Response" in text

    def test_analyze_document_error_is_logged(self, service_factory, tmp_path):
        test_file = tmp_path / "scan.png"
        Image.new("RGB", (10, 10)).save(test_file)
        service = service_factory()
        service.client.analyze_document.side_effect = RuntimeError("boom")

        with pytest.raises(RuntimeError):
            service.analyze_document(test_file)
        [log] = list(cfg.LOGS_DIR.glob("prompt_*.md"))
        assert "## Error\n\nboom" in log.read_text()

    def test_cache_round_trip(self, service_factory, tmp_path):
        test_file = tmp_path / "scan.pdf"
        test_file.write_bytes(b"%PDF fake")
        cache = CacheManager(tmp_path / "cache")
        service = service_factory(cache_manager=cache)

        first = service.analyze_document(test_file)
        service.client.analyze_document = Mock(side_effect=AssertionError("should hit cache"))
        assert service.analyze_document(test_file) == first
