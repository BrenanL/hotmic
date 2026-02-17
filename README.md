# Voice Type

Whisper-powered voice dictation for Windows. Push a hotkey, speak, see live transcription in a small overlay, and either paste into the active window or accumulate notes in a scratchpad file.

## Prerequisites

- **Windows Python 3.10+** — the script must run with Windows Python (not WSL Python) for mic access, hotkeys, and clipboard.
- **uv** (optional but recommended) — for dependency management.

### Install Windows Python (if not already installed)

From WSL or PowerShell:
```bash
powershell.exe -Command "winget install Python.Python.3.12"
```

## Setup

### From WSL

```bash
cd /home/user/tmp/voice-type

# Full path (works immediately):
PYWIN="/mnt/c/Users/User/AppData/Local/Programs/Python/Python312/python.exe"
$PYWIN -m pip install RealtimeSTT keyboard python-dotenv requests

# Or after restarting your WSL session (PATH was updated):
python.exe -m pip install RealtimeSTT keyboard python-dotenv requests
```

### API Key (optional, for future OpenAI API support)

A `.env` file is included with your `OPENAI_API_KEY`. The script loads it automatically via `python-dotenv`.

## Usage

### Start

```bash
# Using the full path:
PYWIN="/mnt/c/Users/User/AppData/Local/Programs/Python/Python312/python.exe"
$PYWIN voice_type.py

# Or after restarting WSL (PATH updated):
python.exe voice_type.py

# With options:
$PYWIN voice_type.py --mode scratchpad --model small --device cuda
```

### Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl+Shift+Space` | Toggle recording on/off |
| `Ctrl+Shift+S` | Switch between Input and Scratchpad mode |

### Modes

**Input mode** (default): When you stop recording, the transcribed text is pasted into whatever window/text field currently has focus. Works like Windows dictation (Win+H).

**Scratchpad mode**: Transcribed text is appended to `scratchpad.txt` with timestamps. The overlay shows your latest dictation. Use this when you want to keep working in other apps and dictate notes on the side.

### Overlay

A small dark bar appears at the bottom of your screen:
- Shows live transcription as you speak
- Status indicator: red dot = recording, yellow = processing, gray = idle
- Displays current mode (INPUT / SCRATCHPAD)
- Does not steal focus from your active application

## CLI Options

```
--mode {input,scratchpad}   Starting mode (default: input)
--hotkey TEXT                Recording hotkey (default: ctrl+shift+space)
--toggle-hotkey TEXT         Mode switch hotkey (default: ctrl+shift+s)
--model TEXT                 Whisper model: tiny/base/small/medium (default: base)
--language TEXT              Language code (default: en)
--scratchpad-file PATH      Scratchpad output path (default: scratchpad.txt)
--device {cpu,cuda}         Inference device (default: cpu)
```

## How It Works

1. On startup, loads two Whisper models via RealtimeSTT: `tiny` for fast live partial results, `base` (or your choice) for accurate final transcription.
2. When you press the hotkey, recording starts. RealtimeSTT transcribes in rolling ~200ms chunks and the overlay updates live.
3. When you press the hotkey again, recording stops and a final transcription pass runs.
4. The final text is either pasted (Input mode) or saved (Scratchpad mode).

## File Structure

```
voice-type/
├── voice_type.py      # Main script
├── pyproject.toml     # Project config / dependencies
├── .env               # API key (gitignored)
├── .gitignore
├── scratchpad.txt     # Created at runtime in scratchpad mode (gitignored)
├── DESIGN.md          # Architecture overview
├── TASKS.md           # Implementation task breakdown
└── README.md          # This file
```
