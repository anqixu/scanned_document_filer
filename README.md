# Document Filer

AI-powered document organization tool that uses Vision Language Models (VLMs) to intelligently rename and file scanned documents.

## Features

- 📄 **Smart Document Analysis**: Uses Claude, GPT-4, or Gemini to analyze document content
- 🎯 **Intelligent Naming**: Suggests descriptive filenames with date extraction
- 📁 **Automatic Organization**: Recommends appropriate folder structures
- 🖼️ **Multi-Format Support**: Handles PDFs and images (PNG, JPG, JPEG, TIFF, TIF, BMP)
- 🔍 **PDF Preview**: Multi-strategy rendering with pdf2image and pypdf fallbacks
- 📏 **Large Image Support**: Automatically handles images >4000px without memory issues
- ✏️ **Manual Override**: Edit any suggestion before filing
- ☑️ **File Selection**: Individual checkboxes for selective processing
- 🔄 **Separate Operations**: Choose to rename in-place or move to new location
- 🚀 **Batch Processing**: Process multiple documents at once with progress tracking
- 📝 **Comprehensive Logging**: Dual logging to temp file (DEBUG) and console (INFO)
- 🔄 **Context Learning**: Generate filing conventions from existing folders
- ⌨️ **Graceful Shutdown**: Clean Ctrl-C handling without ugly tracebacks

## Screenshots

### Main Interface
The PyQt6 GUI provides a modern file browser interface where you can:
- Load folders containing scanned documents (defaults to `~/GDrive/SHARED/__IN__`)
- Preview each document with PDF rendering and large image support
- Select files individually with checkboxes (separate from row selection)
- Process documents in batch with real-time progress
- Review and edit suggested filenames and destinations
- Choose to rename in-place or move to suggested destinations
- See visual feedback (✓/❌) for processing status

## Installation

### Prerequisites

- Python 3.10 or higher
- pip package manager
- poppler-utils (for PDF preview support)

### System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt-get install poppler-utils
```

**macOS:**
```bash
brew install poppler
```

**Windows:**
Download from [poppler releases](https://github.com/oschwartz10612/poppler-windows/releases)

### Setup

1. Clone and navigate to the repository:
```bash
git clone <repository-url>
cd scanned_document_filer
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the package:
```bash
pip install -e ".[dev]"
```

4. Configure your environment:
```bash
cp .env.template .env
```

Edit `.env` and add your API keys:
```bash
# Choose your provider
VLM_PROVIDER=claude  # or openai, or gemini

# Add your API key
ANTHROPIC_API_KEY=sk-ant-...
# or
OPENAI_API_KEY=sk-...
# or
GEMINI_API_KEY=...

# Optional: Set default directories
DEFAULT_SOURCE_DIR=~/GDrive/SHARED/__IN__
DEFAULT_DEST_BASE=~/Documents
```

## Usage

### GUI Application

Launch the graphical interface:

```bash
docfiler-gui
```

Or run directly:
```bash
python -m docfiler.gui.main_window
```

#### Workflow:

1. **Load Files**: 
   - Application auto-loads from `~/GDrive/SHARED/__IN__` if it exists
   - Or click "Open Folder..." to select a different folder
   
2. **Select Files**:
   - Files are checked by default
   - Click checkboxes to select/deselect individual files
   - Use "Select All" / "Select None" buttons for bulk selection
   
3. **Preview**:
   - Click on any file to see preview
   - PDFs render with actual content (if pdf2image available)
   - Large images automatically resize to fit
   
4. **Process**:
   - Click "Process All Files" to analyze selected documents
   - Progress bar shows real-time status
   - Files marked with ✓ (success) or ❌ (error)
   
5. **Review & Edit**:
   - Click each file to review suggestions
   - Edit filename or destination manually
   - See confidence score and reasoning
   
6. **Execute**:
   - **"Rename Selected Files (in place)"**: Renames without moving
   - **"Move Selected Files"**: Moves to suggested destination
   - Confirmation dialog before any operations
   
7. **Logging**:
   - Check console for INFO level logs
   - Full DEBUG logs in `/tmp/docfiler_YYYYMMDD_HHMMSS.log`

### Context Generator (CLI)

Generate a filing context from an existing organized folder structure:

```bash
# Basic usage (defaults to SOURCE_DIR in .env)
docfiler-context

# Analyze specific path
docfiler-context /path/to/organized/documents

# Custom output path (defaults to src/docfiler/data/context.md)
docfiler-context -o my_context.md

# Custom depth and verbosity
docfiler-context /path/to/docs --max-depth 6 --max-files-per-dir 10 -v

# Show help
docfiler-context --help
```

**Options:**
- `path`: Path to folder structure to analyze (defaults to `SOURCE_DIR` in `.env`)
- `-o, --output`: Output file path (defaults to `src/data/context.md`)
- `-v, --verbose`: Enable verbose logging
- `--max-depth`: Maximum folder depth to traverse (default: 8)
- `--max-files_per_dir`: Max example files per directory (default: 100)

This analyzes your existing folder structure and creates a context description that helps the AI understand your filing conventions. The generated context is automatically saved to `src/data/context.md` and loaded by the GUI to provide smarter suggestions.

### Running Tests

Run the test suite:

```bash
pytest
```

With coverage report:
```bash
pytest --cov=docfiler --cov-report=html
```

### Code Quality

Check code style with ruff:

```bash
ruff check .
```

Auto-fix issues:
```bash
ruff check --fix .
```

Format code:
```bash
ruff format .
```

## Configuration

All configuration is done via the `.env` file. See `.env.template` for all available options.

### Key Settings

- `VLM_PROVIDER`: Choose between `claude`, `openai`, or `gemini`
- `IMAGE_DPI`: Target DPI for image conversion (default: 300)
- `MAX_IMAGE_DIMENSION`: Maximum image size in pixels (default: 2048)
- `PDF_PAGES_TO_EXTRACT`: Number of pages to analyze from PDFs (default: 3)
- Model selection for each provider:
  - `CLAUDE_MODEL=claude-3-5-sonnet-20241022`
  - `OPENAI_MODEL=gpt-4o`
  - `GEMINI_MODEL=gemini-2.0-flash-exp`
- `DEFAULT_SOURCE_DIR`: Default folder to load on startup
- `DEFAULT_DEST_BASE`: Base directory for filing operations

## Documentation

Comprehensive documentation is available in the `llms/` directory:

- **[pr.md](llms/pr.md)**: Product requirements, architecture, feature roadmap, and design decisions
- **[engineering.md](llms/engineering.md)**: Engineering practices, coding standards, and technical guidelines
- **[execution.md](llms/execution.md)**: Implementation tracking and active work items
- **[alternatives.md](llms/alternatives.md)**: Local LLM providers, PyTorch classifiers, OCR preprocessing, and hybrid approaches

### Architecture Overview

Document Filer follows a clean three-layer architecture:

```
┌─────────────────────────────────────────┐
│         User Interface Layer            │
│  (PyQt6 GUI, CLI)                       │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│         Service Layer                   │
│  (VLM Service, Image Processor)         │
└─────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│       Integration Layer                 │
│  (API Clients, Config Manager)          │
└─────────────────────────────────────────┘
```

See [llms/pr.md](llms/pr.md) for detailed architecture documentation.

## Project Structure

```
scanned_document_filer/
├── src/
│   ├── docfiler/                  # Main package
│   │   ├── config.py              # Configuration management
│   │   ├── image_processor.py     # PDF/image processing
│   │   ├── api_clients.py         # VLM API clients
│   │   ├── vlm_service.py         # Document analysis service
│   │   ├── gui/                   # PyQt6 GUI
│   │   │   ├── main_window.py     # Main application window
│   │   │   └── file_viewer.py     # Document preview widget
│   │   └── cli/                   # CLI tools
│   │       └── context_generator.py # Context generation tool
│   └── data/                      # Data files (shared)
│       ├── prompt.md              # VLM prompt template
│       └── context.md             # Generated filing context
├── tests/                         # Unit tests
├── llms/                          # Documentation for LLM context
│   └── pr.md                      # Product requirements & architecture
├── pyproject.toml                 # Project configuration
├── .env.template                  # Environment template
└── README.md                      # This file
```

## Recent Improvements (2026-01-01)

### Enhanced User Experience
- ✅ **QListView with QStandardItemModel**: Proper separation of checkbox and selection states
- ✅ **Separate Operations**: "Rename (in place)" vs "Move to destination" buttons
- ✅ **Default Directory**: Auto-loads `~/GDrive/SHARED/__IN__` on startup
- ✅ **Graceful Shutdown**: Clean Ctrl-C handling with proper logging

### Better File Handling
- ✅ **Large Image Support**: PIL pre-processing for images >4000px
- ✅ **PDF Preview**: Multi-strategy rendering (pdf2image → pypdf → fallback)
- ✅ **Compressed PDFs**: Proper handling of encoded/compressed images
- ✅ **Error Resilience**: Graceful degradation when previews fail

### Improved Logging & Debugging
- ✅ **Dual Logging**: Console (INFO) + temp file (DEBUG) with timestamps
- ✅ **Stack Traces**: Full error context in log files
- ✅ **Visual Feedback**: ✓/❌ markers for processing status

### CLI Enhancements
- ✅ **simple-parsing**: Type-safe argument parsing with dataclasses
- ✅ **Configurable Options**: max-depth, max-files-per-dir parameters
- ✅ **Better Help**: Auto-generated from docstrings

### API Updates
- ✅ **google.genai**: Updated from deprecated google.generativeai
- ✅ **pdf2image**: Added as main dependency for better PDF support

## Development

### Engineering Practices

- **Code Style**: Follow ruff formatting and linting rules
- **Testing**: Write unit tests for all new functionality
- **Documentation**: Update pr.md for architectural changes
- **Type Hints**: Use type annotations for all functions
- **Commits**: Write clear, descriptive commit messages

### Adding New Features

1. Update `llms/pr.md` with the feature design
2. Implement the feature following the three-layer architecture
3. Write unit tests
4. Update this README if needed
5. Submit a pull request

## Troubleshooting

### Common Issues

**API Key Errors**
- Ensure your `.env` file has the correct API key for your chosen provider
- Check that `VLM_PROVIDER` matches the provider whose key you've configured

**PDF Preview Not Working**
- Install poppler-utils: `sudo apt-get install poppler-utils` (Ubuntu/Debian)
- Or install pdf2image: `pip install pdf2image`
- Check logs in `/tmp/docfiler_*.log` for details

**Large Image Errors**
- Images >4000px are automatically resized
- If still failing, check DEBUG logs for PIL errors
- Ensure Pillow is up to date: `pip install --upgrade pillow`

**GUI Not Starting**
- Ensure PyQt6 is properly installed: `pip install PyQt6`
- Check Python version is 3.10 or higher
- On WSL, ensure X server is running (e.g., X410, VcXsrv)

**Import Errors**
- Make sure you installed the package: `pip install -e .`
- Activate your virtual environment
- Check that all dependencies are installed

**Checkbox/Selection Issues**
- This was fixed in recent update
- Checkboxes now have separate click area from row selection
- Update to latest version if experiencing issues

**Ctrl-C Not Working**
- Recent update added graceful shutdown
- Press Ctrl-C once and wait for clean exit
- Check logs for "shutting down gracefully" message

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

## License

[Add license information here]

## Acknowledgments

- Built with Claude, GPT-4, and Gemini APIs
- Uses PyQt6 for the GUI
- PDF processing with pypdf and pdf2image
- Image processing with Pillow
- CLI parsing with simple-parsing

## Support

For issues and questions:
- Check the [llms/pr.md](llms/pr.md) for architecture details
- Review existing GitHub issues
- Check logs in `/tmp/docfiler_*.log` for debugging
- Create a new issue with reproduction steps

---

**Version**: 0.1.0 (MVP with Recent Enhancements)
**Status**: Active Development
**Last Updated**: 2026-01-01
