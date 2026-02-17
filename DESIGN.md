# Voice Type - Design Overview

## What This Is

A lightweight voice-to-text dictation tool for Windows that uses Whisper for transcription. It runs as a small overlay at the bottom of the screen, shows live transcription as you speak, and can either paste text into the active window or accumulate it in a scratchpad file.

## Requirements

### Core
- **Hotkey-activated recording**: Global hotkey to start/stop voice capture from any application
- **Live transcription display**: Text appears in a small overlay as the user speaks (not after)
- **Paste-to-active-window mode**: Transcribed text is injected at the cursor in whatever app has focus
- **Scratchpad mode**: Transcribed text accumulates in a running notes file instead of pasting, so the user can keep working in other apps and dictate notes alongside
- **Whisper-powered**: Uses faster-whisper locally (base model) with RealtimeSTT for the streaming feel

### UX
- Overlay sits at the bottom of the screen, always on top, does NOT steal focus
- Visual indicator of recording state (recording / processing / idle)
- Hotkey options: push-to-talk (hold to record) and toggle (press to start/stop)
- Minimal friction — start the script, forget about it, use the hotkey when needed

### Environment
- Runs on Windows Python (not WSL Python) since it needs mic access, global hotkeys, and clipboard
- Developed in WSL, executed via `python.exe`
- No GPU required (CPU inference with faster-whisper base model is fine for 1-2s chunks)

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    voice_type.py                     │
│                                                      │
│  ┌──────────┐   ┌──────────────┐   ┌─────────────┐ │
│  │ keyboard  │──>│ RealtimeSTT  │──>│   Output     │ │
│  │ (hotkey)  │   │ (record +    │   │ (paste or    │ │
│  │           │   │  transcribe) │   │  scratchpad) │ │
│  └──────────┘   └──────┬───────┘   └─────────────┘ │
│                         │                            │
│                         v                            │
│               ┌──────────────────┐                   │
│               │ tkinter overlay  │                   │
│               │ (live text +     │                   │
│               │  status)         │                   │
│               └──────────────────┘                   │
└─────────────────────────────────────────────────────┘
```

### Data Flow

1. User presses hotkey → `keyboard` library fires callback
2. RealtimeSTT starts recording from microphone
3. As audio comes in, RealtimeSTT runs rolling transcription with the `tiny` model and fires `on_realtime_transcription_update` callbacks
4. Each callback updates the tkinter overlay label with partial text
5. When user releases hotkey (or presses again to toggle off), recording stops
6. RealtimeSTT runs a final transcription pass with the `base` model for higher accuracy
7. Final text is either:
   - **Input mode**: Copied to clipboard via `clip.exe`, then `Ctrl+V` simulated into the active window
   - **Scratchpad mode**: Appended to `scratchpad.txt` with a timestamp, and displayed in the overlay

### Key Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| RealtimeSTT | latest | Audio capture + rolling Whisper transcription + VAD |
| faster-whisper | (dep of RealtimeSTT) | Local Whisper inference engine |
| keyboard | latest | Global hotkey registration on Windows |
| tkinter | (stdlib) | Overlay window for live transcription display |
| ctypes | (stdlib) | Win32 API calls to prevent overlay focus stealing |

### Configuration

Hardcoded defaults with CLI arg overrides:

| Setting | Default | Notes |
|---------|---------|-------|
| Mode | `input` | `input` (paste to active window) or `scratchpad` (append to file) |
| Hotkey | `ctrl+shift+space` | Global hotkey for push-to-talk |
| Toggle hotkey | `ctrl+shift+s` | Switch between input/scratchpad mode at runtime |
| Model | `base` | Whisper model for final transcription |
| Realtime model | `tiny` | Whisper model for live partial results (speed matters) |
| Language | `en` | Transcription language |
| Scratchpad file | `scratchpad.txt` | Where scratchpad mode appends text |

## Non-Goals (for now)

- OpenAI Whisper API support (can add later)
- GUI settings panel
- System tray icon
- Comparison/benchmarking mode (user will do this manually)
- Wake word detection
- Multi-language support
