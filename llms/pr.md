# Product Requirements & Architecture

> This document contains the product vision, technical architecture, and implementation status for the Document Filer system.

## Overview

Document Filer is an AI-powered application that organizes scanned documents using Vision Language Models (VLMs). It analyzes document content and suggests intelligence filenames and destination paths based on your existing organizational patterns.

## Core Features

### 1. Document Processing
- **Input Formats**: PDF, PNG, JPG, JPEG, TIFF, BMP.
- **Image Optimization**: Images are downsized to `MAX_IMAGE_DIMENSION` (default 2048px); PDFs render at `IMAGE_DPI` (default 300). Extensions are matched case-insensitively.
- **PDF Strategy**: Renders `PDF_PAGES_TO_EXTRACT` evenly spaced pages (default 3: first, middle, last) with `pdf2image`; the GUI preview falls back to embedded images via `pypdf`.

### 2. AI-Powered Analysis
- **Multi-Provider VLM**: `claude-cli` (Claude Code `claude -p`, default) and `codex-cli` (`codex exec`) use the CLI's subscription login, with no API key. `claude`, `openai` and `gemini` use the provider SDKs and API keys. Selectable in `.env` or the GUI dropdown.
- **Context-Aware**: Learns filing conventions from your existing folder structure.
- **Reasoning**: Provides a brief explanation for every filename and destination suggestion.
- **Extra Instructions**: Customizable `extra_instructions.md` for fine-tuning AI formatting (e.g., date formats, casing).
- **Token Safety**: Built-in limits on the number of folders analyzed during context generation to stay within LLM context windows.
- **Directory Blacklisting**: Configurable `SCAN_IGNORE_PATTERNS` to skip irrelevant or sensitive folders (e.g., `.git`, `node_modules`).

### 3. Desktop GUI (PyQt6)
- **Batch Processing**: Process multiple files simultaneously with progress tracking.
- **Review & Edit**: Interactive preview with the ability to manually override AI suggestions.
- **File Management**: 
  - **Rename**: Batch rename files in their current location.
  - **Move**: Batch file documents into their suggested folder hierarchy under `DEFAULT_DEST_BASE` or `SOURCE_DIR` (auto-creates directories, works across filesystems, never overwrites: a file whose new name already exists, or is shared with another file, is shown in red and refused until renamed).
- **Result Cache**: Suggestions and manual edits are cached in `cache/` by file content hash.
- **Context Integration**: Built-in "Generate Filing Context" button to sync AI conventions with your local directory structure.

### 4. Context Generator
- **CLI & GUI Integrated**: Analyzes existing organized folders to create a `context.md` that guides the VLM.
- **Source-Dir Defaulting**: Uses `SOURCE_DIR` from `.env` as the default repository for learning conventions.

## Architecture

### System Layers

1.  **User Interface Layer**: PyQt6 GUI (`main_window.py`) and CLI (`context_generator.py`).
2.  **Service Layer**: `vlm_service.py` (orchestrator), `image_processor.py` (PDF/Image handling).
3.  **Integration Layer**: `api_clients.py` (one `generate()` per provider: SDK clients plus `claude`/`codex` CLI subprocess clients), `cache_manager.py`, `config.py` (env-based configuration, project paths, logging).
4.  **External Layer**: VLM APIs (Claude, OpenAI, Gemini) or local Claude Code / Codex CLIs.

### Project Structure

```
scanned_document_filer/
├── src/
│   ├── docfiler/              # Main package
│   │   ├── gui/               # PyQt6 application
│   │   ├── cli/               # CLI tools
│   │   └── ...                # Core services
│   └── data/                  # Shared data (Git ignored)
│       ├── prompt.md          # Global VLM prompt template
│       ├── context.md         # Local filing conventions
│       ├── extra_instructions.md # Fine-grained formatting rules
│       └── source_scanned_results.txt # Raw scan audit log
│   └── tests/                 # Unit + GUI test suite
├── logs/                      # Audit trail & prompt caches (Git ignored)
├── cache/                     # Analysis results by content hash (Git ignored)
└── pyproject.toml             # Dependencies & packaging
```

## Implementation Status

### Completed ✅
- [x] Multi-provider VLM factory (Claude, OpenAI, Gemini, Claude Code CLI, Codex CLI) with GUI provider dropdown.
- [x] Consolidated data management in `src/data/`.
- [x] GUI with batch processing, checkboxes, and separate Rename/Move actions.
- [x] Large image handling and robust PDF rendering.
- [x] Background thread for context generation within GUI.
- [x] Logging to a DEBUG `.log` in the system temp dir, and per-request prompt/response caching in `logs/`.
- [x] Graceful Ctrl-C handling and detailed debug logging.
- [x] Simplified CLI with `simple-parsing`.

### Planned Enhancements 🚀
- [ ] Undo/redo for file operations.
- [ ] OCR preprocessing for low-quality non-text scans.
- [ ] Local LLM support (Ollama/LM Studio).
- [ ] Dark mode support.

---
**Version**: 4.0 | **Updated**: 2026-01-01
