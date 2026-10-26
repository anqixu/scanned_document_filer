# Work Tracking & Roadmap

## Completed Milestones ✅

### Core Infrastructure
- [x] Multi-client VLM support with factory pattern.
- [x] Subscription-backed providers via `claude -p` and `codex exec`; provider dropdown in the GUI.
- [x] Environment-based configuration (`.env`).
- [x] Image processing pipeline with high-res PDF rendering (`pdf2image`).

### GUI & User Experience
- [x] File table (checkbox, suggested destination/name, confidence) with shift-click range toggling.
- [x] Separate Rename vs. Move batch operations.
- [x] Preview widget with auto-resizing for large images and robust PDF fallbacks.
- [x] Background thread for document analysis and folder scanning.
- [x] Integrated "Generate Filing Context" button in main window.

### Safety & Auditing
- [x] All logging via the `logging` library to a DEBUG `.log` in the system temp dir; prompt audits in `logs/`.
- [x] Per-request prompt/response Markdown caching.
- [x] Graceful Ctrl-C handling for both GUI and CLI.
- [x] Consolidated `src/data/` for prompts and context (git-ignored).

## Immediate Roadmap 🚀

### High Priority
- [ ] **Undo/Redo**: Track file operations to allow one-click recovery from errors.
- [ ] **OCR Toggle**: Opt-in Tesseract processing for purely graphical/unsearchable scans.
- [ ] **Dark Mode**: High-contrast theme for low-light environments.

### Medium Priority
- [ ] **Local Providers**: Support for Ollama and LM Studio endpoints (`codex exec --oss` may cover this).
- [ ] **Export Results**: Save processed metadata to CSV/JSON before execution.

---
**Updated**: 2026-01-01
