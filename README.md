# Document Filer 🚀

AI-powered document organization tool that uses Vision Language Models (VLMs) to intelligently rename and file scanned documents.

## Features

- 🧠 **Smart Context**: Learns your filing patterns by analyzing your existing folder structure.
- 🎯 **VLM Analysis**: Supports Claude, GPT-4, and Gemini for high-accuracy document understanding.
- 🖼️ **Robust Preview**: High-fidelity PDF rendering (`pdf2image`) and large image support.
- 🖱️ **Interactive Batch GUI**: Multi-file processing with manual overrides and progress tracking.
- 🔄 **Rename vs. Move**: Flexible execution—rename files in-place or move them into organized hierarchies.
- 📋 **Audit Trail**: Detailed project-local logs and per-request prompt/response caching in `logs/`.

## Installation

### Prerequisites
- Python 3.10+
- `poppler-utils` (for PDF rendering)

```bash
# Ubuntu/Debian
sudo apt-get install poppler-utils

# macOS
brew install poppler
```

### Setup
```bash
git clone <repository-url>
cd scanned_document_filer
python -m venv venv
source venv/bin/activate
pip install -e "."
cp .env.template .env
```
*Configure your API keys and `SOURCE_DIR` in `.env`.*

## Usage

### GUI Application
```bash
docfiler-gui
```
1. **Load**: Auto-loads from your configured source directory.
2. **Scan**: Click **"Generate Filing Context"** to sync AI conventions with your existing documents.
3. **Analyze**: Click **"Process Selected Files"** to get naming and destination suggestions.
4. **Execute**: Select files and click **"Rename"** or **"Rename and Move"** to apply changes.

### Context Generator (CLI)
Sync your filing patterns manually:
```bash
docfiler-context
```
*Defaults to using `SOURCE_DIR` from `.env` and saving to `src/data/context.md`.*

## Configuration (.env)

| Key | Description |
|-----|-------------|
| `VLM_PROVIDER` | `claude`, `openai`, or `gemini` |
| `SOURCE_DIR` | Root folder where your organized documents are kept. |
| `DEFAULT_DEST_BASE` | Where suggested documents should be moved to. |
| `VLM_MAX_TOKENS` | Max tokens for VLM response (default: 1024). |

## Customization

You can fine-tune the AI's behavior by editing the files in `src/data/`:

- **`prompt.md`**: The base structural prompt for the VLM.
- **`context.md`**: Automatically generated filing patterns.
- **`extra_instructions.md`**: Manually add your own rules (e.g., "Always use YYYYMMDD format", "Avoid underscores").

## Documentation

- **[pr.md](llms/pr.md)**: Requirements, architecture, and current status.
- **[engineering.md](llms/engineering.md)**: Coding standards and logging practices.
- **[execution.md](llms/execution.md)**: Active work tracking and roadmap.

---
**Version**: 1.0.0 | **Updated**: 2026-01-01
