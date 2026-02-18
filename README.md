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

## Usage

```bash
hotmic                              # default: auto-paste on, fresh overlay
hotmic --no-auto-paste              # start with auto-paste off
hotmic --load-history               # load previous session's history
hotmic --model medium --device cuda # larger model on GPU
hotmic --stop                       # kill a running instance
hotmic --build                      # snapshot source to prod directory
```

### Configuration

Edit `config.toml` in the project directory to change defaults:

```toml
model = "medium"            # final transcription model
realtime-model = "small"    # live preview model (runs every ~200ms)
language = "en"
hotkey = "ctrl+alt+space"
auto-paste = true
max-history = 50
load-history = false
device = "cuda"             # "cpu" or "cuda"
```

CLI arguments override config file values.

#### Whisper Models

| Model | Parameters | VRAM (GPU) | Notes |
|-------|-----------|------------|-------|
| tiny | 39M | ~1 GB | Fast, rough accuracy |
| base | 74M | ~1 GB | Good default for CPU |
| small | 244M | ~2 GB | Good balance |
| medium | 769M | ~5 GB | Very good accuracy |
| large-v3 | 1.5B | ~10 GB | Best accuracy |

Two models run simultaneously: the **realtime model** provides a live preview while you speak (runs inference every ~200ms), and the **final model** does a single accurate pass when you stop recording.

On CPU, keep the realtime model at `tiny` or `base`. On GPU, you can use `small` or even `medium` for realtime without lag.

### Hotkeys

| Hotkey | Action |
|--------|--------|
| `Ctrl+Alt+Space` | Toggle recording on/off |
| `Ctrl+Alt+P` | Toggle auto-paste on/off |
| `Ctrl+Alt+C` | Copy all visible history to clipboard |
| `Ctrl+Alt+H` | Hide/show overlay |
| `Ctrl+Alt+Q` | Quit |

Hotkeys use Win32 `RegisterHotKey` which is immune to Windows killing hooks when elevated processes (like Task Manager) have focus. Hover over the `?` in the overlay to see hotkeys at any time.

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

## Process Management

HotMic writes a PID file to `%LOCALAPPDATA%\HotMic\hotmic.pid` on startup. This enables:

```bash
hotmic --stop         # kill a running instance without hunting through Task Manager
```

On startup, HotMic warns if a previous instance is still running.

### Prod/Dev Split

To avoid breaking your daily driver while editing source:

```bash
hotmic --build        # snapshot voice_type.py + config.toml to %LOCALAPPDATA%\HotMic\prod\
hotmic --install      # Start Menu shortcut points at prod copy (if it exists)
```

- **Dev** (`./hotmic` from terminal) always runs from the source tree
- **Prod** (Start Menu) runs from the frozen snapshot in `%LOCALAPPDATA%\HotMic\prod\`
- Update prod: `hotmic --build && hotmic --install`

## How It Works

1. On startup, loads two Whisper models via RealtimeSTT: a smaller model for fast live preview, and a larger model (both configurable) for accurate final transcription.
2. Press `Ctrl+Alt+Space` to start recording. RealtimeSTT transcribes in rolling ~200ms chunks and the overlay updates live.
3. Press again to stop. A final transcription pass runs with the larger model.
4. The final text is saved to `history.txt`, shown in the overlay, and optionally auto-pasted into the active window.

## Troubleshooting

### GPU not being used (CUDA)

If you set `device = "cuda"` but see this warning on startup:

```
The compute type inferred from the saved model is float16, but the target device
or backend do not support efficient float16 computation.
```

Your PyTorch installation likely doesn't have CUDA support. Check:

```bash
py -3 -c "import torch; print(torch.__version__, 'CUDA:', torch.cuda.is_available())"
```

If it shows `+cpu` or `CUDA: False`, reinstall PyTorch with CUDA:

```bash
py -3 -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
```

Verify with `nvidia-smi` while HotMic is running — you should see `python.exe` processes in the GPU process list.

### Hotkeys not working

HotMic uses Win32 `RegisterHotKey` which requires the hotkey combination to not be registered by another application. If a hotkey fails to register, you'll see an error in the console. Try changing the hotkey in `config.toml`.

### Killing a stuck instance

If HotMic is unresponsive:

```bash
hotmic --stop                 # uses PID file
# or manually:
taskkill /IM python.exe /F    # kills ALL Python processes — use with care
```

## Uninstall

```bash
hotmic --stop             # stop running instance first
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
