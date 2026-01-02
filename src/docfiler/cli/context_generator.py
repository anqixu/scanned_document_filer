"""Context generator for Document Filer.

This script analyzes an existing folder structure to generate a context description
that helps the VLM understand how to organize documents consistently.
"""

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

from ..api_clients import create_client
from ..config import load_config

logger = logging.getLogger(__name__)

# Prompt for generating context from folder structure
CONTEXT_GENERATION_PROMPT = """You are analyzing a document filing system's folder structure.

Your task is to generate a concise context description that will help an AI organize new documents
consistently with this existing structure.

Below is the folder structure and some example filenames:

{folder_info}

Based on this structure, generate a context description that includes:

1. **Filename Convention**: How filenames are encoded (e.g., date format, naming patterns)
2. **Folder Organization**: What categories/subcategories exist and what belongs in each
3. **Examples**: A few examples of the pattern

Keep it concise (max 500 words). Focus on the patterns that would help organize NEW documents.

Respond with ONLY the context description (no JSON, no preamble):
"""


def enumerate_folder_structure(root_path: Path, max_depth: int = 4) -> dict:
    """Enumerate the folder structure and collect information.

    Args:
        root_path: Root directory to analyze.
        max_depth: Maximum depth to traverse.

    Returns:
        Dictionary with folder structure information.
    """
    structure = defaultdict(list)

    for path in root_path.rglob("*"):
        if path.is_file():
            # Calculate relative path and depth
            relative = path.relative_to(root_path)
            depth = len(relative.parts) - 1  # -1 because file itself doesn't count

            if depth <= max_depth:
                parent_dir = str(relative.parent) if relative.parent != Path(".") else "root"
                structure[parent_dir].append(path.name)

    return dict(structure)


def format_folder_info(structure: dict, max_files_per_dir: int = 5) -> str:
    """Format folder structure information for the prompt.

    Args:
        structure: Dictionary of folder -> files.
        max_files_per_dir: Maximum number of example files to show per directory.

    Returns:
        Formatted string describing the structure.
    """
    lines = []
    lines.append("Folder Structure:")
    lines.append("=" * 50)

    for folder, files in sorted(structure.items()):
        lines.append(f"\n{folder}/")
        lines.append(f"  ({len(files)} files)")

        # Show a few example files
        examples = files[:max_files_per_dir]
        for file in examples:
            lines.append(f"  - {file}")

        if len(files) > max_files_per_dir:
            lines.append(f"  ... and {len(files) - max_files_per_dir} more")

    return "\n".join(lines)


def generate_context(root_path: str | Path, output_path: str | Path | None = None) -> str:
    """Generate context by analyzing a folder structure.

    Args:
        root_path: Root directory to analyze.
        output_path: Optional path to save the context. If None, prints to stdout.

    Returns:
        Generated context string.
    """
    root_path = Path(root_path)

    if not root_path.exists() or not root_path.is_dir():
        msg = f"Directory does not exist: {root_path}"
        raise ValueError(msg)

    logger.info(f"Analyzing folder structure: {root_path}")

    # Enumerate folder structure
    structure = enumerate_folder_structure(root_path)

    if not structure:
        logger.warning(f"No files found in {root_path}")
        return "Empty folder structure - no context available."

    # Format for prompt
    folder_info = format_folder_info(structure)
    logger.debug(f"Folder info:\n{folder_info}")

    # Load config and create API client
    config = load_config()
    client = create_client(
        provider=config.vlm_provider,
        api_key=config.active_api_key,
        model=config.active_model,
    )

    # Generate context using LLM
    prompt = CONTEXT_GENERATION_PROMPT.format(folder_info=folder_info)

    logger.info("Sending request to LLM to generate context")

    # For context generation, we don't need images, but our API expects them
    # So we pass an empty list (each client should handle this gracefully)
    # Actually, let me modify this to use a text-only API call

    # Since our VLMClient interface requires images, we'll need a different approach
    # Let's use the provider's native client for text-only requests
    context = _generate_with_provider(config, prompt)

    logger.info("Context generated successfully")

    # Save or print
    if output_path:
        output_path = Path(output_path)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(context)
        logger.info(f"Context saved to: {output_path}")
    else:
        print("\n" + "=" * 50)
        print("Generated Context:")
        print("=" * 50)
        print(context)

    return context


def _generate_with_provider(config, prompt: str) -> str:
    """Generate context using the configured provider.

    Args:
        config: Application configuration.
        prompt: The prompt to send.

    Returns:
        Generated context string.
    """
    provider = config.vlm_provider

    if provider == "claude":
        import anthropic

        client = anthropic.Anthropic(api_key=config.active_api_key)
        response = client.messages.create(
            model=config.active_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    elif provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=config.active_api_key)
        response = client.chat.completions.create(
            model=config.active_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        return response.choices[0].message.content

    elif provider == "gemini":
        import google.generativeai as genai

        genai.configure(api_key=config.active_api_key)
        model = genai.GenerativeModel(config.active_model)
        response = model.generate_content(prompt)
        return response.text

    else:
        msg = f"Unsupported provider: {provider}"
        raise ValueError(msg)


def main():
    """Main entry point for the context generator CLI."""
    parser = argparse.ArgumentParser(
        description="Generate filing context from an existing folder structure"
    )
    parser.add_argument(
        "path",
        type=str,
        help="Path to the folder structure to analyze",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output file path (default: print to stdout)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    try:
        generate_context(args.path, args.output)
    except Exception as e:
        logger.error(f"Error generating context: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
