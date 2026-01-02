# Document Filer

AI-powered document organization tool that uses Vision Language Models (VLMs) to intelligently rename and file scanned documents.

## Features

- 📄 **Smart Document Analysis**: Uses Claude, GPT-4, or Gemini to analyze document content
- 🎯 **Intelligent Naming**: Suggests descriptive filenames with date extraction
- 📁 **Automatic Organization**: Recommends appropriate folder structures
- 🖼️ **Multi-Format Support**: Handles PDFs and images (PNG, JPG, TIFF, BMP)
- ✏️ **Manual Override**: Edit any suggestion before filing
- 🚀 **Batch Processing**: Process multiple documents at once
- 🔄 **Context Learning**: Generate filing conventions from existing folders

## Screenshots

### Main Interface
The PyQt6 GUI provides a file browser interface where you can:
- Load folders containing scanned documents
- Preview each document
- Process documents in batch
- Review and edit suggested filenames and destinations
- Choose to skip files or manually adjust filing locations

## Installation

### Prerequisites

- Python 3.10 or higher
- pip package manager

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd media_server
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

1. Click "Open Folder..." to select a folder with scanned documents
2. Click "Process All Files" to analyze all documents
3. Click on each file to review suggested filename and destination
4. Edit suggestions manually if needed
5. Click "Skip This File" to exclude a file from processing
6. Click "Move/Rename Files" to execute the filing operations

### Context Generator (CLI)

Generate a filing context from an existing organized folder structure:

```bash
docfiler-context /path/to/organized/documents -o context.txt
```

This analyzes your existing folder structure and creates a context description that helps the AI understand your filing conventions.

To use the generated context in the GUI, modify `vlm_service.py` to load your context file, or the context can be integrated into the prompt.

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
- Model selection for each provider (e.g., `CLAUDE_MODEL=claude-3-5-sonnet-20241022`)

## Documentation

Comprehensive documentation is available in the `llms/` directory:

- **[pr.md](llms/pr.md)**: Product requirements, architecture, feature roadmap, and design decisions
- **[engineering.md](llms/engineering.md)**: Engineering practices, coding standards, and technical guidelines
- **[execution.md](llms/execution.md)**: Implementation tracking and active work items
- **[alternatives.md](llms/alternatives.md)**: Local LLM providers, PyTorch classifiers, OCR preprocessing, and hybrid approaches
- **[architecture_diagrams.md](llms/architecture_diagrams.md)**: Auto-generated Mermaid diagrams of code structure

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
docfiler/
├── docfiler/                        # Main package
│   ├── config.py                   # Configuration management
│   ├── image_processor.py          # PDF/image processing
│   ├── api_clients.py              # VLM API clients
│   ├── vlm_service.py              # Document analysis service
│   ├── gui/                        # PyQt6 GUI
│   │   ├── main_window.py
│   │   └── file_viewer.py
│   └── cli/                        # CLI tools
│       └── context_generator.py
├── tests/                          # Unit tests
├── llms/                           # Documentation for LLM context
│   ├── pr.md                       # Product requirements & architecture
│   ├── engineering.md              # Engineering practices
│   ├── execution.md                # Implementation tracking
│   ├── alternatives.md             # Alternative approaches
│   └── architecture_diagrams.md    # Auto-generated diagrams
├── scripts/                        # Utility scripts
│   └── generate_architecture_diagram.py
├── prompt.md                       # VLM prompt template
├── pyproject.toml                  # Project configuration
└── README.md                       # This file
```

## Development

### Engineering Practices

- **Code Style**: Follow ruff formatting and linting rules
- **Testing**: Write unit tests for all new functionality
- **Documentation**: Update design.md for architectural changes
- **Type Hints**: Use type annotations for all functions
- **Commits**: Write clear, descriptive commit messages

### Adding New Features

1. Update `design.md` with the feature design
2. Implement the feature following the three-layer architecture
3. Write unit tests
4. Update this README if needed
5. Submit a pull request

## Troubleshooting

### Common Issues

**API Key Errors**
- Ensure your `.env` file has the correct API key for your chosen provider
- Check that `VLM_PROVIDER` matches the provider whose key you've configured

**Image Processing Errors**
- For PDFs, ensure pypdf can read your file format
- Try reducing `IMAGE_DPI` or `MAX_IMAGE_DIMENSION` for large files

**GUI Not Starting**
- Ensure PyQt6 is properly installed: `pip install PyQt6`
- Check Python version is 3.10 or higher

**Import Errors**
- Make sure you installed the package: `pip install -e .`
- Activate your virtual environment

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
- PDF processing with pypdf
- Image processing with Pillow

## Support

For issues and questions:
- Check the [design.md](design.md) for architecture details
- Review existing GitHub issues
- Create a new issue with reproduction steps

---

**Version**: 0.1.0 (MVP)
**Status**: Development
