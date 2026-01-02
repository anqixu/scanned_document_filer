"""Context generator for Document Filer.

This script analyzes an existing folder structure to generate a context description
that helps the VLM understand how to organize documents consistently.
"""

import logging
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from simple_parsing import ArgumentParser, field
from datetime import datetime
from pathlib import Path

import anthropic
from google import genai
from google.genai import types
from openai import OpenAI
from tqdm import tqdm

from ..api_clients import create_client
from ..config import load_config

logger = logging.getLogger(__name__)


@dataclass
class ContextGeneratorArgs:
    """Arguments for the context generator CLI.
    
    Attributes:
        path: Path to the folder structure to analyze
        output: Output file path (default: print to stdout)
        verbose: Enable verbose logging
        max_depth: Maximum depth to traverse in folder structure
        max_files_per_dir: Maximum number of example files to show per directory
    """
    path: str | None = field(default=None)
    """Path to the folder structure to analyze (defaults to SOURCE_DIR in config)"""
    
    output: str | None = field(default=None, alias="-o")
    """Output file path (defaults to src/data/context.md)"""
    
    verbose: bool = False
    """Enable verbose logging"""
    
    max_depth: int = 8
    """Maximum depth to traverse in folder structure"""
    
    max_files_per_dir: int = 100
    """Maximum number of example files to show per directory"""

# Prompt for generating context from folder structure
CONTEXT_GENERATION_PROMPT = """You are analyzing a document filing system's folder structure.

Your task is to generate a concise context description that will help an AI organize new documents
consistently with this existing structure.

Below is the folder structure and some example filenames. Note that all of these paths are relative to the SOURCE_DIR:

{folder_info}

Based on this structure, generate a context description that includes:

1. **Filename Convention**: How filenames are encoded (e.g., date format, naming patterns)
2. **Folder Organization**: What categories/subcategories exist and what belongs in each. Use relative paths starting from the SOURCE_DIR.
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
    
    logger.info(f"Scanning directory tree: {root_path}")
    logger.info("This may take a while for large directories...")
    
    # Single pass: enumerate and process with progress updates
    file_count = 0
    dir_count = 0
    
    # Use tqdm with dynamic total (we don't know the count ahead of time)
    with tqdm(desc="Scanning", unit=" items", mininterval=0.5) as pbar:
        for path in root_path.rglob("*"):
            pbar.update(1)
            
            if path.is_dir():
                dir_count += 1
                # Update description periodically
                if dir_count % 100 == 0:
                    pbar.set_description(f"Scanning ({file_count} files, {dir_count} dirs)")
            elif path.is_file():
                file_count += 1
                
                # Calculate relative path and depth
                try:
                    relative = path.relative_to(root_path)
                    depth = len(relative.parts) - 1  # -1 because file itself doesn't count

                    if depth <= max_depth:
                        parent_dir = str(relative.parent) if relative.parent != Path(".") else "root"
                        structure[parent_dir].append(path.name)
                except (ValueError, OSError) as e:
                    # Skip files we can't process
                    logger.debug(f"Skipping {path}: {e}")
                    continue
                
                # Update description periodically
                if file_count % 100 == 0:
                    pbar.set_description(f"Scanning ({file_count} files, {dir_count} dirs)")
        
        # Final update
        pbar.set_description(f"Completed ({file_count} files, {dir_count} dirs)")
    
    logger.info(f"Found {file_count} files in {dir_count} directories")
    logger.info(f"Collected {len(structure)} folders within max depth {max_depth}")

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


def generate_context(
    root_path: str | Path,
    output_path: str | Path | None = None,
    max_depth: int = 4,
    max_files_per_dir: int = 5,
) -> str:
    """Generate context by analyzing a folder structure.

    Args:
        root_path: Root directory to analyze.
        output_path: Optional path to save the context. If None, prints to stdout.
        max_depth: Maximum depth to traverse in folder structure.
        max_files_per_dir: Maximum number of example files to show per directory.

    Returns:
        Generated context string.
    """
    root_path = Path(root_path)

    if not root_path.exists() or not root_path.is_dir():
        msg = f"Directory does not exist: {root_path}"
        raise ValueError(msg)

    logger.info(f"Analyzing folder structure: {root_path}")

    # Enumerate folder structure
    structure = enumerate_folder_structure(root_path, max_depth=max_depth)

    if not structure:
        logger.warning(f"No files found in {root_path}")
        return "Empty folder structure - no context available."

    # Format for prompt
    folder_info = format_folder_info(structure, max_files_per_dir=max_files_per_dir)
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
    if not output_path:
        # Default output path is src/data/context.md
        # __file__ is src/docfiler/cli/context_generator.py
        output_path = Path(__file__).parent.parent.parent / "data" / "context.md"
        
    if output_path:
        output_path = Path(output_path)
        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(context)
        logger.info(f"Context saved to: {output_path}")
    
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
        client = anthropic.Anthropic(api_key=config.active_api_key)
        response = client.messages.create(
            model=config.active_model,
            max_tokens=config.vlm_max_tokens * 2,  # Context generation might need more space
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    elif provider == "openai":
        client = OpenAI(api_key=config.active_api_key)
        
        # Determine token parameter based on model
        max_tokens = config.vlm_max_tokens * 2
        params = {
            "model": config.active_model,
            "messages": [{"role": "user", "content": prompt}],
        }
        
        if config.active_model.startswith(("o1-", "gpt-5")):
            params["max_completion_tokens"] = max_tokens
        else:
            params["max_tokens"] = max_tokens
            
        response = client.chat.completions.create(**params)
        return response.choices[0].message.content

    elif provider == "gemini":
        client = genai.Client(api_key=config.active_api_key)
        response = client.models.generate_content(
            model=config.active_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=config.vlm_max_tokens * 2,
            ),
        )
        return response.text

    else:
        msg = f"Unsupported provider: {provider}"
        raise ValueError(msg)


def main():
    """Main entry point for the context generator CLI."""
    parser = ArgumentParser(description="Generate filing context from an existing folder structure")
    parser.add_arguments(ContextGeneratorArgs, dest="args")
    
    args = parser.parse_args().args

    # Configure logging
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_filename = os.path.join(log_dir, f"docfiler_context_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    log_level = logging.DEBUG if args.verbose else logging.INFO
    
    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root_logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    root_logger.addHandler(file_handler)
    
    logger.info(f"Logging to file: {log_filename}")

    # Load config to get default source_dir
    config = load_config()
    scan_path = args.path or config.source_dir
    
    if not scan_path:
        logger.error("No path provided as argument and SOURCE_DIR is not set in .env")
        print("\nError: No path provided. Either:")
        print("1. Pass a path as an argument: docfiler-context /path/to/docs")
        print("2. Set SOURCE_DIR in your .env file")
        sys.exit(1)

    # Expand user home if needed
    scan_path = Path(scan_path).expanduser()
    
    if not scan_path.exists():
        logger.error(f"Path does not exist: {scan_path}")
        sys.exit(1)

    try:
        generate_context(
            scan_path,
            args.output,
            max_depth=args.max_depth,
            max_files_per_dir=args.max_files_per_dir,
        )
    except Exception as e:
        logger.error(f"Error generating context: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
