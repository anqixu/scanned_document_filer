# Engineering Standards & Practices

> This document defines the technical standards and coding principles for the Document Filer project.

## Code Organization

### Imports & Dependencies
- **No Lazy Imports**: All imports must be declared at the top of the file to ensure dependency clarity and fail-fast startup.
- **Explicit Constants**: Prefer explicit constants in `config.py` over hardcoded strings.

### Three-Layer Architecture
1.  **Orchestration (Top)**: Entry points like `main_window.py` and `context_generator.py`. They should read like a high-level table of contents.
2.  **Logic (Middle)**: Core services like `vlm_service.py` that coordinate complex workflows but hide implementation details.
3.  **Functions (Bottom)**: Pure, side-effect-free helpers for URI manipulation, JSON parsing, or image resizing.

## Logging & Auditing

### Unified Directory
- All logs and audit files must reside in the project-root `logs/` directory.
- This directory is git-ignored to prevent leaking sensitive document metadata.

### Prompt Caching
- Every VLM call must be cached in `logs/` with a unique timestamp and filename.
- Format: `logs/prompt_YYYYMMDD_HHMMSS_[filename].md`.
- Content: Full prompt, raw JSON response, and any errors.

## Prompting & Data

### Layered Templates
- **Prompt Base**: `src/data/prompt.md` acts as the structural foundation.
- **Dynamic Context**: `src/data/context.md` provides local folder hierarchy and naming patterns.
- **Extra Instructions**: `src/data/extra_instructions.md` provides user-specific formatting rules (e.g., date formats, naming conventions).
- **Scan Audit**: `src/data/source_scanned_results.txt` tracks all local files/folders seen during context generation.
- **Service Integration**: The `VLMService` must assemble these layers at runtime using placeholder replacement.

## Testing Standards

- **Isolation**: Unit tests must not require active API keys or network access (use mocks).
- **Environment**: Use `pytest-qt` for GUI testing and `pytest-cov` for coverage monitoring.
- **Locations**: Tests are mirroring the `src/docfiler/` structure inside `src/tests/`.

## Code Quality & Linting

- **Tooling**: Use `ruff` for all linting and formatting fixes. Use `ruff check . --fix` regularly.
- **Unused Variables**: Prefer `_` prefix for intentionally unused loop variables or unpacked values.

## Resilience & UX

### CLI Interrupts
- **Two-Stage Stop**: For long-running operations (like filesystem scans), the first `Ctrl+C` should stop the process gracefully and save intermediate results. The second `Ctrl+C` should exit immediately.

### Directory Traversal
- **Depth & Control**: Use `os.walk` with in-place modification of `dirs[:] = []` to enforce recursion limits and implement directory blacklisting efficiently.

### GUI Responsiveness
- **Non-Blocking Logic**: Long-running operations (like VLM analysis or file moves) must run in background threads (`QThread`) to keep the GUI interactive.
- **State Preservation**: UI refreshes should preserve pending user edits or AI suggestions when reloading folder contents.

## Configuration

- **Environment-First**: All secrets and local path configurations (like `SOURCE_DIR`, `VLM_MAX_TOKENS`, and `SCAN_IGNORE_PATTERNS`) go in `.env`.
- **Template Sync**: Ensure `.env.template` is updated whenever a new config key is added.
- **Fail Fast**: The application must validate required API keys and paths at startup.

---
**Version**: 3.0 | **Updated**: 2026-01-01
