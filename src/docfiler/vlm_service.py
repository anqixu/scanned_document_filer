"""VLM service for document analysis and filing suggestions.

Coordinates: cache lookup -> image extraction -> prompt assembly -> VLM call ->
suggestion normalization -> cache save, with every prompt/response logged.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from . import config as cfg
from .api_clients import create_client_from_config
from .cache_manager import CacheManager
from .config import Config
from .image_processor import SUPPORTED_EXTENSIONS, ImageProcessor
from .models import FilingSuggestion

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT = """
This is a general document filing system. Common categories include:

- Finances/Bills (Utility bills, invoices)
- Finances/Statements (Bank statements, credit card statements)
- Medical/Records (Medical records, prescriptions)
- Medical/Insurance (Insurance documents)
- Legal/Contracts (Contracts, agreements)
- Personal/Correspondence (Letters, notices)
- Household/Manuals (Product manuals, warranties)
- Taxes/Receipts (Tax documents, receipts)

Use YYYYMMDD format for dates when visible in documents.
Use clear, descriptive names with Capitalized Words and spaces. Avoid underscores.
"""


def _read_text(path: Path) -> str:
    """Read a stripped text file, or '' if it is missing/unreadable."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except OSError as e:
        logger.error(f"Error reading {path}: {e}")
        return ""


def normalize_filename(filename: str, original: Path) -> str:
    """Make a suggested filename safe to use for original.

    Path separators are replaced (a filename must not move the file), and the
    original extension is enforced (a .jpg must not become .pdf).
    """
    name = filename.replace("/", "-").replace("\\", "-").strip().strip(".")
    if not name:
        return original.name
    suffix = original.suffix
    if name.lower().endswith(suffix.lower()):
        return name[: len(name) - len(suffix)] + suffix
    stem, dot, ext = name.rpartition(".")
    if dot and f".{ext.lower()}" in SUPPORTED_EXTENSIONS:
        name = stem  # drop a wrong document extension the model added
    return name + suffix


def make_suggestion(response: dict, original: Path) -> FilingSuggestion:
    """Build a FilingSuggestion from a raw VLM JSON response."""
    try:
        confidence = float(response.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return FilingSuggestion(
        filename=normalize_filename(str(response.get("filename") or ""), original),
        destination=str(response.get("destination") or "").strip().strip("/\\"),
        confidence=confidence,
        reasoning=str(response.get("reasoning") or "No reasoning provided"),
    )


class VLMService:
    """Service for analyzing documents and suggesting filing locations."""

    def __init__(self, config: Config, context: str | None = None, cache_manager: CacheManager | None = None):
        """Initialize the VLM service.

        Args:
            config: Application configuration.
            context: Filing conventions; defaults to src/data/context.md.
            cache_manager: Optional cache manager for result persistence.
        """
        self.config = config
        self.cache_manager = cache_manager
        self.context = context or self._get_default_context()
        self.image_processor = ImageProcessor(
            target_dpi=config.image_dpi,
            max_dimension=config.max_image_dimension,
            pages_to_extract=config.pdf_pages_to_extract,
        )
        self.client = create_client_from_config(config)
        self.prompt_template = self._load_prompt_template()
        self.extra_instructions = _read_text(cfg.DATA_DIR / "extra_instructions.md")

    def analyze_document(self, file_path: str | Path) -> FilingSuggestion:
        """Analyze a document and suggest filename and destination.

        Raises:
            Exception: If processing or analysis fails.
        """
        file_path = Path(file_path)
        logger.info(f"Analyzing document: {file_path}")

        file_hash = None
        if self.cache_manager:
            try:
                file_hash = self.cache_manager.compute_hash(file_path)
                if cached := self.cache_manager.get_cached_result(file_hash):
                    logger.info(f"Cache hit for {file_path.name}")
                    return cached
            except Exception as e:
                logger.warning(f"Cache lookup failed for {file_path.name}: {e}")

        images = self.image_processor.process_document(file_path)
        logger.debug(f"Extracted {len(images)} image(s) from document")

        prompt = self._build_prompt()
        log_file = self._start_prompt_log(file_path, prompt)
        try:
            response = self.client.analyze_document(prompt, images, max_tokens=self.config.vlm_max_tokens)
        except Exception as e:
            _append(log_file, f"## Error\n\n{e}\n")
            raise
        _append(log_file, f"## Response\n\n```json\n{json.dumps(response, indent=2)}\n```\n")

        suggestion = make_suggestion(response, file_path)
        if self.cache_manager and file_hash:
            self.cache_manager.save_result(file_hash, file_path.name, suggestion)

        logger.info(f"Suggestion: {suggestion}")
        return suggestion

    def _build_prompt(self) -> str:
        """Fill the prompt template with context and extra instructions."""
        return self.prompt_template.replace("{context}", self.context).replace(
            "{extra_instructions}", self.extra_instructions
        )

    def _start_prompt_log(self, file_path: Path, prompt: str) -> Path:
        """Write the prompt to logs/prompt_<timestamp>_<file>.md and return its path."""
        cfg.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in file_path.name if c.isalnum() or c in "._- ")
        log_file = cfg.LOGS_DIR / f"prompt_{datetime.now():%Y%m%d_%H%M%S_%f}_{safe_name}.md"
        log_file.write_text(
            f"# Prompt Cache: {file_path.name}\n\n"
            f"**Timestamp**: {datetime.now().isoformat()}\n"
            f"**File**: {file_path}\n"
            f"**Provider**: {self.config.vlm_provider} ({self.config.active_model or 'default model'})\n\n"
            f"## Prompt\n\n{prompt}\n\n---\n\n",
            encoding="utf-8",
        )
        return log_file

    @staticmethod
    def _load_prompt_template() -> str:
        """Load src/data/prompt.md (required)."""
        path = cfg.DATA_DIR / "prompt.md"
        template = _read_text(path)
        if not template:
            raise FileNotFoundError(f"Prompt template missing or empty: {path}")
        return template

    @staticmethod
    def _get_default_context() -> str:
        """Load src/data/context.md, falling back to a generic context."""
        path = cfg.DATA_DIR / "context.md"
        if content := _read_text(path):
            logger.info(f"Loaded context from {path}")
            return content
        logger.warning(f"No context at {path}; using generic default (run docfiler-context)")
        return DEFAULT_CONTEXT


def _append(path: Path, text: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def create_vlm_service(config: Config, cache_manager: CacheManager | None = None) -> VLMService:
    """Create a VLM service using src/data/context.md as context."""
    return VLMService(config, cache_manager=cache_manager)
