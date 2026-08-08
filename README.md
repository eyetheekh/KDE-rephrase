# Rephrase

Lightweight KDE-integrated text rephraser. Floating palette window, keyboard-first, connects to any OpenAI-compatible API (Groq, OpenAI, etc.).

## Features

- Frameless floating window
- D-Bus integration for KDE global shortcuts
- System tray icon with show/hide toggle

## Requirements

- Python ≥ 3.11
- PyQt6 ≥ 6.11.0
- KDE Plasma (for D-Bus global shortcut integration)

## Setup

```bash
# Install dependencies
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your API credentials
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `API_KEY` | API key for your LLM provider |
| `BASE_URL` | API endpoint (e.g. `https://api.groq.com/openai/v1/chat/completions`) |
| `MODEL_ID` | Model identifier (e.g. `llama-3.3-70b-versatile`) |
| `SYSTEM_INSTRUCTIONS` | System prompt for rephrasing behavior |

## Usage

```bash
python src/main.py
```

### KDE Global Shortcut

Register a global shortcut in System Settings → Shortcuts → Custom Shortcuts:

1. Open **System Settings** → **Shortcuts** → **Custom Shortcuts**
2. Click **Edit** → **New** → **Command/URL**
3. Set **Trigger** to your desired key combo (e.g. `Ctrl+Alt+R`)
4. Set **Command/URL** to:
   ```
   qdbus6 org.kde.rephraser /org/kde/rephraser org.kde.rephraser.MainWindow.showHide
   ```
5. Click **Apply**

> **Note:** The app must be running for the shortcut to work. The D-Bus service registers on launch and is reused by each new instance.

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Submit text for rephrasing |
| `Esc` | Dismiss window |
| `Alt+P` | Toggle show/hide (while window focused) |
| `Tab` | Jump to Copy button (when response visible) |
| `Shift+Tab` | Move focus backwards |

## Project Structure

```
src/
  main.py         # UI, D-Bus adaptor, system tray, entry point
  chat.py         # OpenAI-compatible API client
```
