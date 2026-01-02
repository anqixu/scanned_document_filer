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

## Testing Standards

- **Isolation**: Unit tests must not require active API keys or network access (use mocks).
- **Environment**: Use `pytest-qt` for GUI testing and `pytest-cov` for coverage monitoring.
- **Locations**: Tests are mirroring the `src/docfiler/` structure inside `src/tests/`.

## Configuration

- **Environment-First**: All secrets and local path configurations (like `SOURCE_DIR`) go in `.env`.
- **Template Sync**: Ensure `.env.template` is updated whenever a new config key is added.
- **Fail Fast**: The application must validate required API keys and paths at startup.

---
**Version**: 2.0 | **Updated**: 2026-01-01
