# Product Requirements & Architecture

> This document contains the product vision, technical architecture, and implementation status for the Document Filer system.

## Overview

Document Filer is an AI-powered application that organizes scanned documents using Vision Language Models (VLMs). It analyzes document content and suggests intelligence filenames and destination paths based on your existing organizational patterns.

## Core Features

### 1. Document Processing
- **Input Formats**: PDF, PNG, JPG, JPEG, TIFF, BMP.
- **Image Optimization**: Automatic resizing of large images (>4000px) and configurable DPI (default: 300).
- **PDF Strategy**: Multi-strategy rendering using `pdf2image` and `pypdf`. Extracts first, middle, and last pages for optimal context vs. cost balance.

### 2. AI-Powered Analysis
- **Multi-Provider VLM**: Supports Claude (Anthropic), GPT-4 (OpenAI), and Gemini (Google).
- **Context-Aware**: Learns filing conventions from your existing folder structure.
- **Reasoning**: Provides a brief explanation for every filename and destination suggestion.
- **Configurable Limits**: API token limits (`VLM_MAX_TOKENS`) are externalized to `.env` for easy tuning.
- **Extra Instructions**: Customizable `extra_instructions.md` for fine-tuning AI formatting (e.g., date formats, casing).

### 3. Desktop GUI (PyQt6)
- **Batch Processing**: Process multiple files simultaneously with progress tracking.
- **Review & Edit**: Interactive preview with the ability to manually override AI suggestions.
- **File Management**: 
  - **Rename**: Batch rename files in their current location.
  - **Move**: Batch file documents into their suggested folder hierarchy (auto-creates directories).
- **Context Integration**: Built-in "Generate Filing Context" button to sync AI conventions with your local directory structure.

### 4. Context Generator
- **CLI & GUI Integrated**: Analyzes existing organized folders to create a `context.md` that guides the VLM.
- **Source-Dir Defaulting**: Uses `SOURCE_DIR` from `.env` as the default repository for learning conventions.

## Architecture

### System Layers

1.  **User Interface Layer**: PyQt6 GUI (`main_window.py`) and CLI (`context_generator.py`).
2.  **Service Layer**: `vlm_service.py` (orchestrator), `image_processor.py` (PDF/Image handling).
3.  **Integration Layer**: `api_clients.py` (provider-specific abstraction), `config.py` (env-based configuration).
4.  **External Layer**: VLM APIs (Claude, OpenAI, Gemini).

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
│       └── extra_instructions.md # Fine-grained formatting rules
├── logs/                      # Audit trail & prompt caches (Git ignored)
├── tests/                     # Unit test suite
└── pyproject.toml             # Dependencies & packaging
```

## Implementation Status

### Completed ✅
- [x] Multi-provider VLM factory (Claude, OpenAI, Gemini).
- [x] Consolidated data management in `src/data/`.
- [x] GUI with batch processing, checkboxes, and separate Rename/Move actions.
- [x] Large image handling and robust PDF rendering.
- [x] Background thread for context generation within GUI.
- [x] Project-local logging and per-request prompt/response caching in `logs/`.
- [x] Graceful Ctrl-C handling and detailed debug logging.
- [x] Simplified CLI with `simple-parsing`.

### Planned Enhancements 🚀
- [ ] Undo/redo for file operations.
- [ ] OCR preprocessing for low-quality non-text scans.
- [ ] Local LLM support (Ollama/LM Studio).
- [ ] Dark mode support.

---
**Version**: 4.0 | **Updated**: 2026-01-01
