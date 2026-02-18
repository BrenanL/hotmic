# Voice Type

Whisper-powered voice dictation for Windows. Push a hotkey, speak, see live transcription in a small overlay. All transcriptions are saved to a persistent history log. Optionally auto-pastes into the active window, or just accumulates — click any entry to copy it.

## Prerequisites

- **Windows Python 3.10+** — must run with Windows Python (not WSL Python) for mic access, hotkeys, and clipboard.

### Install Windows Python (if not already installed)

From WSL or PowerShell:
```bash
powershell.exe -Command "winget install Python.Python.3.12"
```

## Setup

```bash
cd /home/user/tmp/voice-type

# Full path (works immediately):
PYWIN="/mnt/c/Users/User/AppData/Local/Programs/Python/Python312/python.exe"
$PYWIN -m pip install RealtimeSTT keyboard python-dotenv requests

# Or after restarting your WSL session (PATH was updated):
python.exe -m pip install RealtimeSTT keyboard python-dotenv requests
```

## Usage

### Start

```bash
PYWIN="/mnt/c/Users/User/AppData/Local/Programs/Python/Python312/python.exe"

# Default: auto-paste on, fresh overlay
$PYWIN voice_type.py

# Start with auto-paste off
$PYWIN voice_type.py --no-auto-paste

# Load previous session's history into the overlay
$PYWIN voice_type.py --load-history

# Use a larger model on GPU
$PYWIN voice_type.py --model small --device cuda
```

### Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl+Alt+Space` | Toggle recording on/off |
| `Ctrl+Alt+P` | Toggle auto-paste on/off |
| `Ctrl+Alt+C` | Copy all visible history to clipboard |
| `Ctrl+Alt+H` | Hide/show overlay |
| `Ctrl+Alt+Q` | Quit |

All hotkeys are suppressed — they won't pass through to other applications.

### Auto-Paste

When **auto-paste is on** (green "PASTE ON" indicator), finished transcriptions are automatically pasted into whatever window has focus via `Ctrl+V`.

When **auto-paste is off** (red "PASTE OFF" indicator), transcriptions are captured and shown in the overlay but nothing is pasted. Use this when you want to dictate notes while working in other apps without text appearing in random places.

Toggle with `Ctrl+Alt+P` at any time, even mid-session.

### History

Every transcription is always saved to `history.txt` with a full timestamp, regardless of auto-paste setting. The file grows indefinitely and is never modified by the tool — it's your permanent log.

The overlay shows the most recent entries (up to `--max-history`, default 50). You can:

- **Click any entry** to copy just that one to the clipboard (entry flashes to confirm)
- **[Copy All]** button or `Ctrl+Alt+C` to copy all visible entries, newline-separated
- **[Clear]** button to clear the overlay display (does not touch the file)

**Workflow example:** Turn off auto-paste, dictate several quick notes, hit `Ctrl+Alt+C` to copy them all, paste into a document.

### Overlay

A dark bar at the bottom of the screen:
- Live transcription as you speak
- Status dot: red = recording, yellow = processing, gray = idle
- Auto-paste indicator (green ON / red OFF)
- [Copy All] and [Clear] buttons
- Click any history entry to copy it
- Draggable — click and drag to reposition
- `Ctrl+Alt+H` to hide (shows a tiny dot in the top-right corner so you know it's still running)
- Does not steal focus from your active application

## CLI Options

```
--hotkey TEXT            Recording hotkey (default: ctrl+alt+space)
--model TEXT             Whisper model: tiny/base/small/medium (default: base)
--language TEXT           Language code (default: en)
--history-file PATH      History log path (default: history.txt)
--max-history N          Max entries shown in overlay (default: 50)
--load-history           Load previous session's history on launch
--no-auto-paste          Start with auto-paste disabled
--device {cpu,cuda}      Inference device (default: cpu)
```

## How It Works

1. On startup, loads two Whisper models via RealtimeSTT: `tiny` for fast live partial results, `base` (configurable) for accurate final transcription.
2. Press `Ctrl+Alt+Space` to start recording. RealtimeSTT transcribes in rolling ~200ms chunks and the overlay updates live.
3. Press again to stop. A final transcription pass runs with the larger model.
4. The final text is saved to `history.txt`, shown in the overlay, and optionally auto-pasted into the active window.

## File Structure

```
voice-type/
├── voice_type.py      # Main script
├── pyproject.toml     # Project config / dependencies
├── .env               # API key (gitignored)
├── .gitignore
├── history.txt        # Persistent transcription log (gitignored)
├── DESIGN.md          # Architecture overview
├── TASKS.md           # Implementation task breakdown
└── README.md          # This file
```
