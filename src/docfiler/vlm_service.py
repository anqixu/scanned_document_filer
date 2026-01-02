"""VLM service for document analysis and filing suggestions.

This module coordinates the workflow of processing documents and getting
filename and destination suggestions from VLM providers.
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .api_clients import create_client
from .config import Config
from .image_processor import ImageProcessor

logger = logging.getLogger(__name__)


@dataclass
class FilingSuggestion:
    """Represents a filing suggestion for a document."""

    filename: str
    destination: str
    confidence: float
    reasoning: str

    def __str__(self) -> str:
        """String representation of the suggestion."""
        return f"{self.destination}/{self.filename}"


class VLMService:
    """Service for analyzing documents and suggesting filing locations."""

    def __init__(self, config: Config, context: str | None = None):
        """Initialize the VLM service.

        Args:
            config: Application configuration.
            context: Optional context about folder structure and filing conventions.
        """
        self.config = config
        self.context = context or self._get_default_context()

        # Initialize image processor
        self.image_processor = ImageProcessor(
            target_dpi=config.image_dpi,
            max_dimension=config.max_image_dimension,
        )

        # Initialize API client
        self.client = create_client(
            provider=config.vlm_provider,
            api_key=config.active_api_key,
            model=config.active_model,
        )

        # Load prompt template and extra instructions
        self.prompt_template = self._load_prompt_template()
        self.extra_instructions = self._load_extra_instructions()

    def analyze_document(self, file_path: str | Path) -> FilingSuggestion:
        """Analyze a document and suggest filename and destination.

        Args:
            file_path: Path to the document file.

        Returns:
            FilingSuggestion with suggested filename and destination.

        Raises:
            Exception: If processing or analysis fails.
        """
        file_path = Path(file_path)
        logger.info(f"Analyzing document: {file_path}")

        # Process document to images
        images = self.image_processor.process_document(file_path)
        logger.debug(f"Extracted {len(images)} image(s) from document")

        # Build prompt with context
        prompt = self._build_prompt()

        # Cache prompt to logs/
        log_dir = Path(__file__).parent.parent.parent / "logs"
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_filename = "".join(x for x in file_path.name if x.isalnum() or x in "._- ")
        cache_file = log_dir / f"prompt_{timestamp}_{safe_filename}.md"

        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(f"# Prompt Cache: {file_path.name}\n\n")
            f.write(f"**Timestamp**: {datetime.now().isoformat()}\n")
            f.write(f"**File**: {file_path}\n\n")
            f.write("## Prompt\n\n")
            f.write(prompt)
            f.write("\n\n---\n\n")

        # Send to VLM for analysis
        try:
            response = self.client.analyze_document(
                prompt,
                images,
                max_tokens=self.config.vlm_max_tokens
            )

            # Append response to cache
            with open(cache_file, "a", encoding="utf-8") as f:
                f.write("## Response\n\n")
                f.write("```json\n")
                f.write(json.dumps(response, indent=2))
                f.write("\n```\n")
        except Exception as e:
            # Log error to cache
            with open(cache_file, "a", encoding="utf-8") as f:
                f.write(f"## Error\n\n{e}\n")
            raise

        # Create suggestion from response
        suggestion = FilingSuggestion(
            filename=response.get("filename", "untitled.pdf"),
            destination=response.get("destination", "unsorted"),
            confidence=response.get("confidence", 0.0),
            reasoning=response.get("reasoning", "No reasoning provided"),
        )

        logger.info(f"Suggestion: {suggestion}")
        return suggestion

    def _build_prompt(self) -> str:
        """Build the complete prompt with context and extra instructions.

        Returns:
            Complete prompt string.
        """
        prompt = self.prompt_template.replace("{context}", self.context)
        prompt = prompt.replace("{extra_instructions}", self.extra_instructions)
        return prompt

    def _load_prompt_template(self) -> str:
        """Load the prompt template from prompt.md.

        Returns:
            Prompt template content.
        """
        # Look for prompt.md in the data directory
        prompt_path = Path(__file__).parent.parent / "data" / "prompt.md"

        if prompt_path.exists():
            with open(prompt_path, encoding="utf-8") as f:
                return f.read()
        else:
            logger.warning(f"Prompt template not found at {prompt_path}, using default")
            return self._get_default_prompt()

    def _load_extra_instructions(self) -> str:
        """Load extra instructions from extra_instructions.md.

        Returns:
            Extra instructions content, or empty string if not found.
        """
        extra_path = Path(__file__).parent.parent / "data" / "extra_instructions.md"

        if extra_path.exists():
            try:
                with open(extra_path, encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as e:
                logger.error(f"Error loading extra instructions from {extra_path}: {e}")

        return ""

    def _get_default_prompt(self) -> str:
        """Get default prompt template if prompt.md doesn't exist.

        Returns:
            Default prompt string.
        """
        return """You are an AI assistant helping to organize scanned documents.

Context: {context}

{extra_instructions}

Analyze the provided document image(s) and suggest:
1. A descriptive filename
2. An appropriate destination folder path

Respond with JSON:
{
  "filename": "YYYYMMDD Description.ext",
  "destination": "Category/Subcategory",
  "confidence": 0.95,
  "reasoning": "Brief explanation"
}
"""

    def _get_default_context(self) -> str:
        """Get default context if none provided.
        
        Attempts to load from data/context.md first.
        
        Returns:
            Context string.
        """
        # Look for context.md in the data directory
        context_path = Path(__file__).parent.parent / "data" / "context.md"

        if context_path.exists():
            try:
                with open(context_path, encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        logger.info(f"Loaded context from {context_path}")
                        return content
            except Exception as e:
                logger.error(f"Error loading context from {context_path}: {e}")

        # Fallback to hardcoded default
        return """
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


def create_vlm_service(config: Config, context_path: str | Path | None = None) -> VLMService:
    """Factory function to create a VLM service.

    Args:
        config: Application configuration.
        context_path: Optional path to a context file.

    Returns:
        Initialized VLMService.
    """
    context = None

    if context_path:
        context_path = Path(context_path)
        if context_path.exists():
            with open(context_path, encoding="utf-8") as f:
                context = f.read()
        else:
            logger.warning(f"Context file not found: {context_path}")

    return VLMService(config, context)
