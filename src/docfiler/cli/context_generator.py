"""Context generator for Document Filer.

Scans an existing, organized folder tree and asks the LLM to summarize its
filing conventions into src/data/context.md, which guides later suggestions.
"""

import logging
import os
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from simple_parsing import ArgumentParser, field
from tqdm import tqdm

from .. import config as cfg
from ..api_clients import create_client_from_config, smoke_test
from ..config import PROVIDERS, Config, load_config, setup_logging

logger = logging.getLogger(__name__)

DEFAULT_MAX_DEPTH = 8
DEFAULT_MAX_FILES_PER_DIR = 100
MAX_FOLDERS = 2000  # cap on folders sent to the LLM
MAX_FOLDER_INFO_CHARS = 200_000  # ~50k tokens; examples per folder shrink to fit


@dataclass
class ContextGeneratorArgs:
    """Arguments for the context generator CLI."""

    path: str | None = field(default=None)
    """Folder structure to analyze (defaults to SOURCE_DIR)"""

    output: str | None = field(default=None, alias="-o")
    """Output file path (defaults to src/data/context.md)"""

    provider: str | None = field(default=None)
    """Override VLM_PROVIDER, e.g. claude-cli or codex-cli"""

    verbose: bool = False
    """Enable verbose logging"""

    max_depth: int = DEFAULT_MAX_DEPTH
    """Maximum depth to traverse in folder structure"""

    max_files_per_dir: int = DEFAULT_MAX_FILES_PER_DIR
    """Maximum number of example files to show per directory"""


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


def _walk(root_path: Path, max_depth: int, regexes: list[re.Pattern]) -> Iterator[tuple[Path, list[str]]]:
    """Yield (relative_dir, files) for each directory up to max_depth.

    A directory is skipped (with its subtree) when its name fully matches an
    ignore pattern, so "CV" skips a folder named CV but not "CVS Receipts".
    """
    for root, dirs, files in os.walk(root_path):
        rel = Path(root).relative_to(root_path)
        if len(rel.parts) >= max_depth:
            dirs[:] = []
        else:
            dirs[:] = sorted(d for d in dirs if not any(r.fullmatch(d) for r in regexes))
        yield rel, files


def enumerate_folder_structure(
    root_path: Path,
    max_depth: int = DEFAULT_MAX_DEPTH,
    ignore_patterns: list[str] | None = None,
) -> dict[str, list[str]]:
    """Map each folder (relative path, "root" for the top) to its file names.

    The first Ctrl+C stops the scan and keeps what was collected so far.
    A raw listing is also written to src/data/source_scanned_results.txt.
    """
    regexes = [re.compile(p) for p in (ignore_patterns or [])]
    structure: dict[str, list[str]] = {}
    raw_results: list[str] = []
    file_count = 0

    logger.info(f"Scanning directory tree: {root_path}")
    # Single pass; no up-front count (that would double the filesystem walk)
    with tqdm(desc="Analyzing structure", unit="dirs", mininterval=0.5) as pbar:
        try:
            for rel, files in _walk(root_path, max_depth, regexes):
                pbar.update(1)
                raw_results.append(f"DIR: {rel}")
                key = "root" if rel == Path(".") else str(rel)
                if files:
                    structure[key] = files
                    file_count += len(files)
                    raw_results.extend(f"FILE: {rel / f}" for f in files)
                label = key if len(key) <= 25 else f"...{key[-22:]}"
                pbar.set_postfix(files=file_count, dir=label)
        except KeyboardInterrupt:
            logger.info("Scan interrupted by user. Proceeding with data collected so far...")
            logger.info("Press Ctrl+C again to exit immediately.")

    results_path = cfg.DATA_DIR / "source_scanned_results.txt"
    try:
        results_path.parent.mkdir(parents=True, exist_ok=True)
        header = (
            f"# Raw Scan Results (Max Depth: {max_depth})\n# Root: {root_path}\n"
            f"# Timestamp: {datetime.now().isoformat()}\n{'-' * 50}\n"
        )
        results_path.write_text(header + "\n".join(raw_results), encoding="utf-8")
        logger.info(f"Raw scan results saved to {results_path}")
    except OSError as e:
        logger.warning(f"Failed to save raw results: {e}")

    logger.info(f"Found {file_count} files in {len(structure)} folders (max depth {max_depth})")
    return structure


def format_folder_info(
    structure: dict[str, list[str]],
    max_files_per_dir: int = DEFAULT_MAX_FILES_PER_DIR,
    max_folders: int = MAX_FOLDERS,
    max_chars: int = MAX_FOLDER_INFO_CHARS,
) -> str:
    """Format folder structure for the prompt, within a character budget.

    Every folder (up to max_folders) is listed with its file count; the number
    of example filenames per folder is reduced until the text fits max_chars.
    """
    folders = sorted(structure.items())
    header = ["Folder Structure:", "=" * 50]
    if len(folders) > max_folders:
        logger.warning(f"Too many folders ({len(folders)}). Limiting to {max_folders}.")
        header.append(f"(Showing first {max_folders} folders out of {len(folders)})")
        folders = folders[:max_folders]

    def render(per_dir: int) -> str:
        lines = list(header)
        for folder, files in folders:
            lines += [f"\n{folder}/", f"  ({len(files)} files)"]
            lines += [f"  - {f}" for f in sorted(files)[:per_dir]]
            if len(files) > per_dir:
                lines.append(f"  ... and {len(files) - per_dir} more")
        return "\n".join(lines)

    limits = [n for n in (max_files_per_dir, 50, 20, 10, 5, 3, 1, 0) if n <= max_files_per_dir]
    for per_dir in limits:
        text = render(per_dir)
        if len(text) <= max_chars:
            break
    if per_dir < max_files_per_dir:
        logger.info(f"Showing up to {per_dir} example files per folder to fit the prompt budget")
    return text


def generate_context(
    root_path: str | Path,
    config: Config,
    output_path: str | Path | None = None,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_files_per_dir: int = DEFAULT_MAX_FILES_PER_DIR,
) -> str:
    """Scan root_path, generate filing context with the LLM, and save it.

    Args:
        root_path: Root directory to analyze.
        config: Application configuration (selects the provider).
        output_path: Where to save the context (default src/data/context.md).
        max_depth: Maximum depth to traverse.
        max_files_per_dir: Maximum example files to show per directory.

    Returns:
        Generated context string.
    """
    root_path = Path(root_path).expanduser()
    if not root_path.is_dir():
        raise ValueError(f"Directory does not exist: {root_path}")

    client = create_client_from_config(config)  # fail fast before the slow scan
    structure = enumerate_folder_structure(root_path, max_depth, config.scan_ignore_patterns)
    if not structure:
        raise ValueError(f"No files found in {root_path}")

    folder_info = format_folder_info(structure, max_files_per_dir=max_files_per_dir)
    logger.debug(f"Folder info:\n{folder_info}")

    logger.info(f"Sending request to {client.name} to generate context")
    prompt = CONTEXT_GENERATION_PROMPT.format(folder_info=folder_info)
    context = client.generate(prompt, [], config.vlm_max_tokens * 2).strip()
    if not context:
        raise ValueError("LLM returned an empty context")

    output_path = Path(output_path) if output_path else cfg.DATA_DIR / "context.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(context, encoding="utf-8")
    logger.info(f"Context saved to: {output_path}")
    return context


def main():
    """Main entry point for the context generator CLI."""
    parser = ArgumentParser(description="Generate filing context from an existing folder structure")
    parser.add_arguments(ContextGeneratorArgs, dest="args")
    args = parser.parse_args().args

    log_file = setup_logging("docfiler_context", logging.DEBUG if args.verbose else logging.INFO)
    logger.info(f"Logging to file: {log_file}")

    try:
        config = load_config()
        if args.provider:
            config = config.with_provider(args.provider)
    except ValueError as e:
        logger.error(f"Configuration error: {e}. Valid providers: {', '.join(PROVIDERS)}")
        sys.exit(1)

    scan_path = args.path or config.source_dir
    if not scan_path:
        logger.error("No path provided. Either pass --path /path/to/docs or set SOURCE_DIR in .env")
        sys.exit(1)
    scan_path = Path(scan_path).expanduser()
    if not scan_path.is_dir():
        logger.error(f"Path does not exist: {scan_path}")
        sys.exit(1)

    # Fail fast on bad credentials before the (potentially slow) directory scan
    try:
        smoke_test(create_client_from_config(config))
    except (RuntimeError, ValueError) as e:
        logger.error(f"Provider check failed: {e}")
        sys.exit(1)

    try:
        generate_context(scan_path, config, args.output, args.max_depth, args.max_files_per_dir)
    except Exception as e:
        logger.error(f"Error generating context: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
