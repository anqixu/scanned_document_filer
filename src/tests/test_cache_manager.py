"""Unit tests for cache manager."""

from docfiler.cache_manager import CacheManager
from docfiler.models import FilingSuggestion

SUGGESTION = FilingSuggestion("20240101 Bill.pdf", "Finances", 0.9, "bill")


def test_hash_is_content_based(tmp_path):
    a, b, c = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    a.write_bytes(b"same")
    b.write_bytes(b"same")
    c.write_bytes(b"other")
    assert CacheManager.compute_hash(a) == CacheManager.compute_hash(b) != CacheManager.compute_hash(c)


def test_round_trip_and_gui_state(tmp_path):
    cache = CacheManager(tmp_path)
    assert not cache.has_entry("h") and not cache.has_entry(None)
    assert cache.get_cached_result("h") is None

    cache.save_result("h", "scan.pdf", SUGGESTION)
    assert cache.has_entry("h")
    assert cache.get_cached_result("h") == SUGGESTION

    cache.save_gui_state("h", "Edited.pdf", "Personal")
    assert cache.get_cached_result("h") == FilingSuggestion("Edited.pdf", "Personal", 0.9, "bill")

    cache.save_result("h", "scan.pdf", SUGGESTION)  # a fresh result clears edits
    assert cache.get_cached_result("h") == SUGGESTION


def test_gui_state_without_entry_is_noop(tmp_path):
    cache = CacheManager(tmp_path)
    cache.save_gui_state("missing", "x.pdf", "y")
    assert not cache.has_entry("missing")


def test_corrupt_entry_returns_none(tmp_path):
    (tmp_path / "bad.json").write_text("{not json")
    assert CacheManager(tmp_path).get_cached_result("bad") is None
