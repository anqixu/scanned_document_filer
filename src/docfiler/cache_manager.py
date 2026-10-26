"""Content-addressed disk cache for document analysis results.

Layout: cache/{sha256}.json holding the VLM suggestion plus any GUI edits
("gui_state"), keyed by the SHA-256 of the file content so entries survive
renames.
"""

import hashlib
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .config import CACHE_DIR
from .models import FilingSuggestion

logger = logging.getLogger(__name__)


class CacheManager:
    """Content-addressed cache for document analysis results."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compute_hash(file_path: Path) -> str:
        """SHA-256 of full file content."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(1 << 20):
                h.update(chunk)
        return h.hexdigest()

    def _path(self, file_hash: str) -> Path:
        return self.cache_dir / f"{file_hash}.json"

    def has_entry(self, file_hash: str | None) -> bool:
        """Return True if a cache entry exists for this hash."""
        return bool(file_hash) and self._path(file_hash).exists()

    def get_cached_result(self, file_hash: str) -> FilingSuggestion | None:
        """Return the cached suggestion with any GUI edits applied, or None on miss/corruption."""
        path = self._path(file_hash)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            suggestion = FilingSuggestion(**data["suggestion"])
            if gui_state := data.get("gui_state"):
                suggestion.filename = gui_state["filename"]
                suggestion.destination = gui_state["destination"]
            return suggestion
        except Exception as e:
            logger.warning("Cache read failed for %s: %s", file_hash, e)
            return None

    def save_result(self, file_hash: str, original_filename: str, suggestion: FilingSuggestion) -> None:
        """Store a fresh VLM suggestion (clears any previous GUI edits)."""
        data = {
            "file_hash": file_hash,
            "original_filename": original_filename,
            "cached_at": _now(),
            "suggestion": asdict(suggestion),
            "gui_state": None,
        }
        self._write(file_hash, data)

    def save_gui_state(self, file_hash: str, filename: str, destination: str) -> None:
        """Record user edits on an existing entry (no-op if there is no entry)."""
        path = self._path(file_hash)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("gui_state save failed for %s: %s", file_hash, e)
            return
        data["gui_state"] = {"filename": filename, "destination": destination, "updated_at": _now()}
        self._write(file_hash, data)

    def _write(self, file_hash: str, data: dict) -> None:
        """Atomic write: temp file then os.replace()."""
        target = self._path(file_hash)
        tmp = target.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, target)
        except Exception as e:
            logger.warning("Cache write failed for %s: %s", file_hash, e)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_cache_manager() -> CacheManager:
    """Create a CacheManager rooted at the project cache/ directory."""
    return CacheManager(CACHE_DIR)
