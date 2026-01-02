"""VLM service for document analysis and filing suggestions.

This module coordinates the workflow of processing documents and getting
filename and destination suggestions from VLM providers.
"""

import logging
from dataclasses import dataclass
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

        # Load prompt template
        self.prompt_template = self._load_prompt_template()

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

        # Send to VLM for analysis
        response = self.client.analyze_document(prompt, images)

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
        """Build the complete prompt with context.

        Returns:
            Complete prompt string.
        """
        return self.prompt_template.replace("{context}", self.context)

    def _load_prompt_template(self) -> str:
        """Load the prompt template from prompt.md.

        Returns:
            Prompt template content.
        """
        # Look for prompt.md in the data directory
        prompt_path = Path(__file__).parent / "data" / "prompt.md"

        if prompt_path.exists():
            with open(prompt_path, encoding="utf-8") as f:
                return f.read()
        else:
            logger.warning(f"Prompt template not found at {prompt_path}, using default")
            return self._get_default_prompt()

    def _get_default_prompt(self) -> str:
        """Get default prompt template if prompt.md doesn't exist.

        Returns:
            Default prompt string.
        """
        return """You are an AI assistant helping to organize scanned documents.

Context: {context}

Analyze the provided document image(s) and suggest:
1. A descriptive filename (format: YYYY-MM-DD_description.ext)
2. An appropriate destination folder path

Respond with JSON:
{
  "filename": "YYYY-MM-DD_description.ext",
  "destination": "category/subcategory",
  "confidence": 0.95,
  "reasoning": "Brief explanation"
}
"""

    def _get_default_context(self) -> str:
        """Get default context if none provided.

        Returns:
            Default context string.
        """
        return """
This is a general document filing system. Common categories include:

- finances/bills (utility bills, invoices)
- finances/statements (bank statements, credit card statements)
- medical/records (medical records, prescriptions)
- medical/insurance (insurance documents)
- legal/contracts (contracts, agreements)
- personal/correspondence (letters, notices)
- household/manuals (product manuals, warranties)
- taxes/receipts (tax documents, receipts)

Use YYYY-MM-DD format for dates when visible in documents.
Use clear, descriptive names with underscores instead of spaces.
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
