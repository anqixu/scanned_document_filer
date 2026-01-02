# Engineering Practices & Principles

> This document defines the engineering standards, code organization principles, and technical preferences for the Document Filer project. When editing code or making technical decisions, refer to this document for guidance.

## Document Structure Reference

This repository uses a structured documentation approach:
- **pr.md**: Product requirements, architecture, feature roadmap, and open design decisions
- **engineering.md**: This file - engineering practices and coding standards
- **execution.md**: Implementation tracking and active work items

When looking for information:
- Product features and architecture → **pr.md**
- Coding standards and technical decisions → **engineering.md**
- What's being worked on → **execution.md**

---

## Code Organization Principles

### 1. Three-Layer Architecture

**Top Layer** (Human-Readable Orchestration)
- High-level function calls that read like prose
- No implementation details exposed
- Entry points and workflow coordination
- Examples: `main_window.py`, `context_generator.py`

**Middle Layer** (Integrated Components)
- Business logic and workflow management
- Integration of multiple low-level components
- Domain-specific operations
- Examples: `vlm_service.py`, `image_processor.py`, `api_clients.py`

**Bottom Layer** (Unit-Testable Functions)
- Pure functions with single responsibility
- No side effects when possible
- Highly testable in isolation
- Examples: Configuration validation, image resizing, JSON parsing

### 2. Naming Conventions

- **Files**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions**: `snake_case`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private members**: `_leading_underscore`
- **Test files**: `test_<module_name>.py`

### 3. Documentation Standards

**Docstrings**
- All public functions and classes must have docstrings
- Use Google-style docstrings format
- Include Args, Returns, Raises sections

Example:
```python
def process_document(file_path: str | Path) -> list[bytes]:
    """Process a document file and return image data.

    Args:
        file_path: Path to the document file (PDF or image).

    Returns:
        List of image data as bytes (PNG format).

    Raises:
        ValueError: If file format is unsupported.
        FileNotFoundError: If file does not exist.
    """
```

**Type Hints**
- All function signatures must include type hints
- Use modern Python type hints (e.g., `list[str]` not `List[str]`)
- Use union types with `|` operator (e.g., `str | None`)

**Comments**
- Only for non-obvious logic
- Prefer self-documenting code over comments
- Avoid redundant comments that restate the code

**Project Documentation**
- README.md: User-facing setup and usage
- pr.md: Product requirements and architecture
- engineering.md: This document
- execution.md: Implementation tracking

---

## Testing Strategy

### Unit Tests
- Test individual functions in isolation
- One assertion per test when possible
- Clear test names: `test_<function>_<scenario>_<expected>`

Example:
```python
def test_resize_image_width_larger():
    """Test resizing when width exceeds max dimension."""
```

### Test Coverage
- Aim for >80% coverage
- Focus on business logic over boilerplate
- Use `pytest --cov=docfiler --cov-report=html`

### Test Data
- Minimal, representative test cases
- Use fixtures for reusable test data
- Mock external dependencies (APIs, file system when appropriate)

### Test Organization
```
tests/
├── __init__.py
├── test_config.py          # Config loading tests
├── test_image_processor.py # Image/PDF processing tests
├── test_api_clients.py     # API client tests
└── test_vlm_service.py     # VLM service integration tests
```

---

## Code Quality

### Linting and Formatting

**Ruff Configuration**
- Line length: 100 characters maximum
- Target Python version: 3.10
- Enabled rules: E, W, F, I, B, C4, UP
- Auto-fix safe issues: `ruff check --fix .`
- Format code: `ruff format .`

### Code Complexity
- Keep functions small and focused (<50 lines ideal)
- Maximum cyclomatic complexity: 10
- Extract complex logic into helper functions
- Prefer composition over inheritance

### Dependency Management
- Minimal dependencies
- Well-maintained packages only
- Pin major versions in pyproject.toml
- Regular security updates

---

## Version Control

### Commit Messages
- Use descriptive, atomic commits
- Format: `<type>: <description>`
- Types: feat, fix, docs, refactor, test, chore

Examples:
```
feat: add support for TIFF image processing
fix: handle empty PDF files gracefully
docs: update README with installation instructions
refactor: extract JSON parsing logic into helper
test: add tests for config validation
```

### Branch Strategy
- Feature branches for development
- Branch naming: `feature/<description>` or `fix/<issue>`
- Keep branches short-lived
- Rebase before merging to maintain linear history

### Pull Requests
- Clear description of changes
- Reference related issues
- Include test coverage
- Request review before merge

### Tags
- Version releases: `v0.1.0`, `v0.2.0`, etc.
- Follow semantic versioning

---

## Error Handling

### Exceptions
- Use built-in exceptions when appropriate
- Create custom exceptions for domain-specific errors
- Include helpful error messages

```python
class DocumentProcessingError(Exception):
    """Raised when document cannot be processed."""
    pass
```

### Validation
- Validate inputs at system boundaries (API calls, user input, file operations)
- Fail fast with clear error messages
- Use type hints and runtime checks

### Logging
- Structured logging with appropriate levels
- DEBUG: Detailed diagnostic information
- INFO: General operational messages
- WARNING: Unexpected but recoverable situations
- ERROR: Serious problems requiring attention

```python
import logging

logger = logging.getLogger(__name__)
logger.info(f"Processing document: {file_path}")
logger.error(f"Failed to process {file_path}: {error}", exc_info=True)
```

### User Feedback
- Clear error messages in GUI
- Avoid technical jargon in user-facing messages
- Provide actionable guidance

---

## Configuration Management

### Environment Variables
- Store secrets and configuration in .env
- Provide .env.template with examples
- Never commit .env to version control

### Defaults
- Sensible defaults for all configuration
- Override capability via environment variables
- Document all configuration options

### Validation
- Check configuration on startup
- Fail fast with helpful error messages
- Validate API keys and external dependencies

---

## Performance Considerations

### Image Processing
- Resize images before sending to APIs
- Use efficient PIL operations
- Consider memory usage for large batches

### API Calls
- Minimize token usage (3 pages vs. entire PDF)
- Implement rate limiting if needed
- Handle timeouts and retries gracefully

### GUI Responsiveness
- Use background threads for long operations
- Update progress indicators
- Allow user to cancel operations

---

## Security Practices

### API Keys
- Never hardcode API keys
- Use environment variables
- Validate keys on startup

### File Operations
- Validate file paths before operations
- Prevent path traversal attacks
- Handle permissions errors gracefully

### User Input
- Sanitize file paths and names
- Validate destination paths
- Prevent injection attacks

---

## Alternative Implementation Approaches

### Local LLM Providers

**Considerations:**
- **Privacy**: Data stays local, no cloud transmission
- **Cost**: No API usage fees after initial setup
- **Performance**: Depends on hardware, generally slower than cloud APIs
- **Accuracy**: May be lower than GPT-4 or Claude for vision tasks

**Recommended Providers:**
1. **Ollama**: Easy setup, good model selection
2. **LM Studio**: GUI-based, beginner-friendly
3. **vLLM**: High performance, server-grade
4. **LocalAI**: OpenAI-compatible API, good integration

**Integration Strategy:**
- Add `LocalLLMClient` class implementing `VLMClient` interface
- Support OpenAI-compatible API endpoints
- Configurable via .env: `LOCAL_LLM_URL`, `LOCAL_LLM_MODEL`

**Vision-Capable Models:**
- LLaVA (7B-13B): Good balance of speed and accuracy
- BakLLaVA: Improved vision understanding
- CogVLM: Strong document understanding
- LLaVA-NeXT: Latest generation, better performance

**Comparison:**
| Aspect | Cloud VLM | Local LLM |
|--------|-----------|-----------|
| Setup Complexity | Low | High |
| Privacy | Low | High |
| Cost per Document | $0.01-0.05 | $0 (after setup) |
| Accuracy | High | Medium |
| Speed | Fast | Medium-Slow |
| Hardware Requirements | None | GPU recommended |

### PyTorch/Transformers Classifier Approach

**Use Case:**
- Predefined categories only (no open-ended filing)
- Large volume processing (cost sensitive)
- Offline operation requirement
- Custom training on proprietary documents

**Architecture:**
```
Document → OCR (Tesseract) → Text Embedding → Classifier → Category + Filename Pattern
       → Image Features → Vision Model →
```

**Components:**
1. **OCR Preprocessing**: Tesseract to extract text
2. **Text Encoder**: BERT/DistilBERT for text embedding
3. **Vision Encoder**: ResNet/ViT for image features
4. **Fusion Layer**: Combine text + vision features
5. **Classifier Head**: Multi-label classification for categories
6. **Filename Generator**: Rule-based or small seq2seq model

**Pros:**
- No API costs after training
- Complete offline operation
- Customizable to specific use case
- Fast inference on GPU

**Cons:**
- Requires training data (hundreds of examples per category)
- Limited to predefined categories
- Setup and training complexity
- Less flexible than VLM approach

**Implementation Path:**
1. Create `docfiler/ml/` module
2. Implement `OCRProcessor` using pytesseract
3. Implement `DocumentClassifier` using transformers
4. Add training script with sample data
5. Update GUI to support both VLM and classifier modes

### Hybrid Approach

**Best of Both Worlds:**
- Use VLM for initial filing and category discovery
- Train classifier on user-corrected examples
- Fall back to VLM for novel document types
- Use classifier for high-volume batch processing

**Implementation:**
```python
class HybridFilingService:
    def __init__(self, vlm_service, classifier_service):
        self.vlm = vlm_service
        self.classifier = classifier_service

    def suggest_filing(self, document):
        # Try classifier first (fast, cheap)
        if self.classifier.is_trained():
            suggestion = self.classifier.predict(document)
            if suggestion.confidence > 0.9:
                return suggestion

        # Fall back to VLM for uncertain cases
        return self.vlm.analyze_document(document)
```

---

## OCR Preprocessing Pipeline

### When to Use OCR
- Scanned documents (not native PDFs)
- Low-quality images
- Handwritten documents
- Non-English text requiring translation
- Cost optimization (text cheaper than vision)

### Implementation Approach

**Option 1: Always Preprocess**
- Run OCR on all documents
- Send text + images to VLM
- VLM uses text as primary source, images for verification

**Option 2: Selective Preprocessing**
- Detect if PDF has embedded text
- Only OCR image-based documents
- Configuration flag to enable/disable

**Option 3: Fallback Strategy**
- Try VLM on images first
- If low confidence, retry with OCR text
- User can force OCR in GUI

### Recommended Setup

```python
class OCRPreprocessor:
    """OCR preprocessing using Tesseract."""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled

    def extract_text(self, image_bytes: bytes) -> str:
        """Extract text from image using Tesseract."""
        if not self.enabled:
            return ""

        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img)
        return text.strip()
```

**Integration:**
```python
# In vlm_service.py
if self.config.ocr_enabled:
    ocr_text = self.ocr_processor.extract_text(images[0])
    prompt = prompt.replace("{ocr_text}", ocr_text)
```

**Performance Impact:**
- OCR adds 1-3 seconds per page
- Tesseract supports GPU acceleration
- Consider parallel processing for batches

---

**Document Version**: 1.0
**Last Updated**: 2026-01-01
**Maintained By**: Engineering Team
