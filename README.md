# HotMic

Whisper-powered voice dictation for Windows. Push a hotkey, speak, see live transcription in a small overlay. All transcriptions are saved to a persistent history log. Optionally auto-pastes into the active window, or just accumulates — click any entry to copy it.

## Quick Start

### Windows (native)

```
git clone https://github.com/BrenanL/hotmic.git
cd hotmic
hotmic.bat --install
```

### WSL

```bash
git clone https://github.com/BrenanL/hotmic.git
cd hotmic
./hotmic --install
```

The installer auto-detects Python, installs dependencies, and sets up:
- **Win+S:** type "HotMic" and hit Enter (no terminal needed)
- **Terminal:** `hotmic` (WSL) or `hotmic.bat` (Windows) from any directory

### Prerequisites

- **Windows Python 3.10+** — if not installed:
  ```
  winget install Python.Python.3.12
  ```
- **WSL** (Ubuntu or similar) — only needed if using the WSL launcher
- **Administrator privileges** — the `keyboard` library requires admin to register global hotkeys. Run your terminal as administrator, or right-click the Start Menu shortcut and choose "Run as administrator".

## Usage

```bash
hotmic                              # default: auto-paste on, fresh overlay
hotmic --no-auto-paste              # start with auto-paste off
hotmic --load-history               # load previous session's history
hotmic --model small --device cuda  # larger model on GPU
```

### Configuration

Edit `config.toml` in the project directory to change defaults:

```toml
model = "base"
language = "en"
hotkey = "ctrl+alt+space"
auto-paste = true
max-history = 50
load-history = false
device = "cpu"
```

CLI arguments override config file values.

### Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl+Alt+Space` | Toggle recording on/off |
| `Ctrl+Alt+P` | Toggle auto-paste on/off |
| `Ctrl+Alt+C` | Copy all visible history to clipboard |
| `Ctrl+Alt+H` | Hide/show overlay |
| `Ctrl+Alt+Q` | Quit |

All hotkeys are suppressed — they won't pass through to other applications. Hover over the `?` in the overlay to see hotkeys at any time.

### Auto-Paste

When **auto-paste is on** (green "PASTE ON" indicator), finished transcriptions are automatically pasted into whatever window has focus via `Ctrl+V`.

When **auto-paste is off** (red "PASTE OFF" indicator), transcriptions are captured and shown in the overlay but nothing is pasted. Use this when you want to dictate notes while working in other apps without text appearing in random places.

Toggle with `Ctrl+Alt+P` at any time, even mid-session.

### History

Every transcription is always saved to `history.txt` with a full timestamp, regardless of auto-paste setting. The file grows indefinitely and is never modified by the tool — it's your permanent log.

The overlay shows the most recent entries (up to `max-history`, default 50). You can:

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
- `?` tooltip showing all hotkeys
- Click any history entry to copy it
- Draggable — click and drag to reposition
- `Ctrl+Alt+H` to hide (shows a tiny dot in the top-right corner so you know it's still running)
- Does not steal focus from your active application

## How It Works

1. On startup, loads two Whisper models via RealtimeSTT: `tiny` for fast live partial results, `base` (configurable) for accurate final transcription.
2. Press `Ctrl+Alt+Space` to start recording. RealtimeSTT transcribes in rolling ~200ms chunks and the overlay updates live.
3. Press again to stop. A final transcription pass runs with the larger model.
4. The final text is saved to `history.txt`, shown in the overlay, and optionally auto-pasted into the active window.

## Uninstall

```bash
hotmic --uninstall        # WSL
hotmic.bat --uninstall    # Windows
```

Removes the Start Menu shortcut and app data. The project folder is left untouched.

## File Structure

```
hotmic/
├── hotmic             # Launcher script (WSL/bash)
├── hotmic.bat         # Launcher script (Windows-native)
├── voice_type.py      # Main script
├── config.toml        # User configuration
├── hotmic.ico         # App icon
├── pyproject.toml     # Project metadata / dependencies
├── LICENSE            # MIT license
├── .gitignore
├── tools/
│   └── gen_icon.py    # Icon generator (requires Pillow)
└── README.md
```

## License

MIT
