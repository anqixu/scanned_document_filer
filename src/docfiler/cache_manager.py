"""Content-addressed disk cache for document analysis results.

Cache layout (project_root/cache/):
  {sha256}.json          — metadata + suggestion + gui_state
  {sha256}_page0.png     — extracted page images
  {sha256}_page1.png
  ...
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class CacheManager:
    """Content-addressed cache for document analysis results."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def compute_hash(self, file_path: Path) -> str:
        """SHA-256 of full file content (64 KB chunks)."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    def has_entry(self, file_hash: str) -> bool:
        """Return True if a JSON cache entry exists for this hash."""
        if not file_hash:
            return False
        return (self.cache_dir / f"{file_hash}.json").exists()

    def get_cached_result(
        self, file_hash: str
    ):
        """Return (images, suggestion, gui_state) or None if miss/corrupt.

        images is a list[bytes], suggestion is a FilingSuggestion-like dict,
        gui_state is a dict or None.
        """
        try:
            json_path = self.cache_dir / f"{file_hash}.json"
            if not json_path.exists():
                return None

            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)

            # Import here to avoid circular imports
            from .vlm_service import FilingSuggestion

            suggestion_data = data["suggestion"]
            suggestion = FilingSuggestion(
                filename=suggestion_data["filename"],
                destination=suggestion_data["destination"],
                confidence=suggestion_data["confidence"],
                reasoning=suggestion_data["reasoning"],
            )

            # Load images
            image_count = data.get("image_count", 0)
            images = []
            for i in range(image_count):
                img_path = self.cache_dir / f"{file_hash}_page{i}.png"
                if img_path.exists():
                    images.append(img_path.read_bytes())

            gui_state = data.get("gui_state")
            return images, suggestion, gui_state

        except Exception as e:
            logger.warning("Cache read failed for %s: %s", file_hash, e)
            return None

    def save_result(
        self,
        file_hash: str,
        original_filename: str,
        images: list,
        suggestion,
    ) -> None:
        """Write images then JSON atomically.

        Images are written first; if interrupted, the absent JSON means
        the partial entry is ignored on next read.
        """
        try:
            # Write images first
            for i, img_bytes in enumerate(images):
                img_path = self.cache_dir / f"{file_hash}_page{i}.png"
                self._atomic_write_bytes(img_path, img_bytes)

            # Write JSON
            data = {
                "file_hash": file_hash,
                "original_filename": original_filename,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "image_count": len(images),
                "suggestion": {
                    "filename": suggestion.filename,
                    "destination": suggestion.destination,
                    "confidence": suggestion.confidence,
                    "reasoning": suggestion.reasoning,
                },
                "gui_state": None,
            }
            json_path = self.cache_dir / f"{file_hash}.json"
            self._atomic_write_json(json_path, data)

        except Exception as e:
            logger.warning("Cache write failed for %s: %s", file_hash, e)

    def save_gui_state(self, file_hash: str, filename: str, destination: str) -> None:
        """Overwrite gui_state in existing JSON entry."""
        try:
            json_path = self.cache_dir / f"{file_hash}.json"
            if not json_path.exists():
                return

            with open(json_path, encoding="utf-8") as f:
                data = json.load(f)

            data["gui_state"] = {
                "filename": filename,
                "destination": destination,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self._atomic_write_json(json_path, data)

        except Exception as e:
            logger.warning("gui_state save failed for %s: %s", file_hash, e)

    def _atomic_write_bytes(self, target: Path, data: bytes) -> None:
        """Write to .tmp then os.replace() — atomic on POSIX and Windows/DrvFs."""
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)

    def _atomic_write_json(self, target: Path, data: dict) -> None:
        """Same pattern for JSON."""
        tmp = target.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, target)


def create_cache_manager() -> CacheManager:
    """Create a CacheManager rooted at project_root/cache/."""
    cache_dir = Path(__file__).parent.parent.parent / "cache"
    return CacheManager(cache_dir)
