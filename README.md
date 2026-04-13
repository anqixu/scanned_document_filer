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

**Note: Never create a `venv` inside the project directory.** Always use a centralized virtual environment, specifically at `$HOME/venv/local/` (or `%USERPROFILE%\venv\local\` on Windows).

1. Clone the repository and navigate to it:
   ```bash
   git clone <repository-url>
   cd scanned_document_filer
   ```

2. Activate your central virtual environment. If it doesn't exist, create it first:

   **Linux / macOS:**
   ```bash
   # Create if it doesn't exist
   mkdir -p ~/venv
   python3 -m venv ~/venv/local

   # Activate
   source ~/venv/local/bin/activate
   ```

   **Windows (Command Prompt / PowerShell):**
   ```powershell
   # Create if it doesn't exist
   New-Item -ItemType Directory -Force -Path "$HOME\venv"
   python -m venv "$HOME\venv\local"

   # Activate
   & "$HOME\venv\local\Scripts\Activate.ps1"
   ```

3. Install dependencies and set up `.env` file:
   ```bash
   pip install -e "."
   cp .env.template .env
   # Depending on your terminal in Windows, you may need to use:
   # copy .env.template .env
   ```
*Configure your API keys and `SOURCE_DIR` in `.env`.*

### WSL2 with X410 (Windows)

The GUI (`docfiler-gui`) requires an X display server on WSL2. [X410](https://x410.dev/) is a recommended option.

**1. Install required packages in WSL2:**
```bash
sudo apt-get install libxcb-xinerama0 libxcb-cursor0 libgl1
```

**2. Launch X410** on Windows in *"Windowed Apps"* or *"Desktop"* mode.
Enable *"Allow Public Access"* in X410 settings (or accept the firewall rule prompt).

**3. Set the `DISPLAY` variable in WSL2:**

For X410 with default WSL2 (NAT networking):
```bash
export DISPLAY=$(grep -m1 nameserver /etc/resolv.conf | awk '{print $2}'):0
```

For Windows 11 / WSL2 with mirrored networking (`networkingMode=mirrored` in `.wslconfig`):
```bash
export DISPLAY=localhost:0
```

Add the appropriate line to your `~/.bashrc` or `~/.zshrc` so it persists.

**4. Verify the display works:**
```bash
xdpyinfo | head -5   # should print display info without errors
```

**5. Run the GUI:**
```bash
docfiler-gui
```

The application auto-detects `DISPLAY` and sets `QT_QPA_PLATFORM=xcb` accordingly — no extra Qt flags needed.

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
