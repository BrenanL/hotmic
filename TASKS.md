# Voice Type - Implementation Tasks

## Phase 1: Project Setup

### Task 1.1: Create project structure and dependencies
- Create `requirements.txt` with: `RealtimeSTT`, `keyboard`
- Create `voice_type.py` as the single entry-point script
- Add a `README.md` stub with install/run instructions (Windows Python + pip)
- Note: tkinter and ctypes are stdlib, no pip needed

### Task 1.2: Verify Windows Python can be invoked from WSL
- Test that `python.exe` is accessible from WSL after install
- Test that `pip.exe install` works from WSL
- Document the setup steps for future reference

---

## Phase 2: Overlay Window

### Task 2.1: Create the tkinter overlay window
- Frameless window (`overrideredirect(True)`)
- Positioned at bottom-center of screen
- Size: ~800x80px (wide enough for a sentence, short enough to not obstruct)
- Dark background (`#1a1a2e` or similar), white text
- Semi-transparent (`-alpha 0.85`)
- Always on top (`-topmost`)

### Task 2.2: Prevent focus stealing with Win32 API
- After window creation, use `ctypes.windll.user32` to set `WS_EX_NOACTIVATE` and `WS_EX_TOOLWINDOW` extended styles on the window handle
- This is critical: without it, every overlay update would yank focus from the user's active app
- Test by clicking on overlay — it should NOT become the focused window

### Task 2.3: Add overlay UI elements
- **Status indicator**: Small colored dot or text label — red = recording, yellow = processing, gray = idle
- **Transcription text**: Large label area showing current transcription, with word wrap
- **Mode indicator**: Small text showing current mode ("INPUT" or "SCRATCHPAD")
- Use `label.config(text=...)` for updates — no need for a text widget at this stage

### Task 2.4: Add overlay update method
- Create a thread-safe `update_display(text, status)` function
- Since RealtimeSTT callbacks come from a different thread, use `root.after()` or a queue to marshal updates to the tkinter main thread
- Status enum: `IDLE`, `RECORDING`, `PROCESSING`

---

## Phase 3: RealtimeSTT Integration

### Task 3.1: Initialize RealtimeSTT recorder
- Wrap in `if __name__ == '__main__':` (required on Windows due to multiprocessing)
- Configure with:
  - `model="base"` for final transcription
  - `realtime_model_type="tiny"` for fast partial results
  - `enable_realtime_transcription=True`
  - `language="en"`
  - `device="cpu"` (default, user can change if they have CUDA)
  - Tune `post_speech_silence_duration` for natural pause handling

### Task 3.2: Wire up transcription callbacks
- `on_realtime_transcription_update`: Update overlay with partial text, set status to RECORDING
- `on_recording_start`: Set status to RECORDING
- `on_recording_stop`: Set status to PROCESSING
- Final text callback (via `recorder.text(callback)`): Deliver final text to output handler, set status to IDLE

### Task 3.3: Handle the recording lifecycle
- Recording needs to be manually started/stopped based on hotkey (not continuous VAD)
- On hotkey press: call `recorder.start()`
- On hotkey release (or toggle off): call `recorder.stop()`, then `recorder.text(callback)` for final result
- Need to coordinate with RealtimeSTT's internal VAD — may need to configure or disable auto-stop so that recording only stops on hotkey, not on silence

---

## Phase 4: Hotkey System

### Task 4.1: Register global hotkeys
- Use `keyboard` library to register the push-to-talk hotkey
- Default: `ctrl+shift+space`
- On key down → start recording
- On key up → stop recording and trigger final transcription
- Also register a mode-toggle hotkey (`ctrl+shift+s`) to switch input/scratchpad

### Task 4.2: Handle hotkey edge cases
- Debounce: ignore rapid repeated presses
- Guard against starting a new recording while one is still processing
- If already recording, a press should stop (not start a second recording)

---

## Phase 5: Output Handlers

### Task 5.1: Implement input mode (paste to active window)
- After final transcription completes:
  1. Copy text to Windows clipboard using `subprocess.run(['clip.exe'], input=text.encode(), check=True)` (accessible from both WSL and Windows Python)
  2. Simulate `Ctrl+V` using `keyboard.send('ctrl+v')`
- Small delay (~50ms) between clipboard write and paste to ensure it propagates
- The overlay shows the text briefly, then clears after paste

### Task 5.2: Implement scratchpad mode (append to file)
- After final transcription:
  1. Append to `scratchpad.txt` with ISO timestamp prefix
  2. Keep the text visible in the overlay (don't clear it)
- File format:
  ```
  [2026-02-16 10:23:45] This is what the user said in the first dictation.
  [2026-02-16 10:24:12] And this is the next thing they said.
  ```
- The overlay shows the latest entry (or last N lines if space allows)

### Task 5.3: Implement mode switching
- `ctrl+shift+s` toggles between input and scratchpad mode
- Overlay updates the mode indicator immediately
- No interruption to recording if one is in progress

---

## Phase 6: Main Loop and Wiring

### Task 6.1: Wire everything together in `voice_type.py`
- Entry point parses CLI args (mode, hotkey, model, language, scratchpad path)
- Initialize RealtimeSTT recorder
- Initialize tkinter overlay
- Register hotkeys
- Start tkinter main loop
- Threading: tkinter runs on main thread, RealtimeSTT runs its own threads internally, hotkey callbacks bridge between them via a queue

### Task 6.2: Handle graceful shutdown
- `Ctrl+C` or closing the overlay exits cleanly
- Stop any active recording
- Shut down RealtimeSTT recorder
- Clean up keyboard hooks

---

## Phase 7: Polish and Testing

### Task 7.1: Test on Windows
- Verify mic recording works
- Verify hotkey fires from any application
- Verify overlay does not steal focus
- Verify paste works into Notepad, VS Code, browser text fields
- Verify scratchpad file writes correctly

### Task 7.2: Add CLI argument parsing
- `--mode input|scratchpad`
- `--hotkey` (default `ctrl+shift+space`)
- `--model` (default `base`)
- `--language` (default `en`)
- `--scratchpad-file` (default `scratchpad.txt`)
- `--device` (default `cpu`, option for `cuda`)
- Use `argparse`

### Task 7.3: Write install/run instructions
- Document in README:
  1. Install Windows Python (`winget install Python.Python.3.12`)
  2. `pip.exe install -r requirements.txt`
  3. `python.exe voice_type.py`
  4. Hotkey reference

---

## Dependency Graph

```
1.1 ─────────────────────────────────────┐
                                          v
1.2 ──> 2.1 ──> 2.2 ──> 2.3 ──> 2.4 ──> 6.1 ──> 7.1
                                          ^
        3.1 ──> 3.2 ──> 3.3 ────────────┤
                                          │
        4.1 ──> 4.2 ────────────────────┤
                                          │
        5.1 ──> 5.2 ──> 5.3 ────────────┘
                                          │
                                          v
                                         6.2 ──> 7.2 ──> 7.3
```

Phases 2, 3, 4, and 5 can be developed in parallel since they're independent modules. Phase 6 integrates them. Phase 7 is testing and polish.
