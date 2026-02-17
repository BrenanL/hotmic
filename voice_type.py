"""Voice Type — Whisper-powered voice dictation for Windows.

A lightweight overlay that captures speech via hotkey, shows live transcription,
and either pastes into the active window or appends to a scratchpad file.

Must be run with Windows Python (python.exe), not WSL Python.
"""

import argparse
import ctypes
import datetime
import os
import platform
import queue
import threading
import time
import tkinter as tk
from enum import Enum, auto
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Status(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


class Mode(Enum):
    INPUT = "input"
    SCRATCHPAD = "scratchpad"


# ---------------------------------------------------------------------------
# Overlay Window
# ---------------------------------------------------------------------------

class Overlay:
    """Transparent always-on-top overlay for live transcription display."""

    BG = "#1a1a2e"
    FG_TEXT = "#e0e0e0"
    FG_DIM = "#888888"
    STATUS_COLORS = {
        Status.IDLE: "#555555",
        Status.RECORDING: "#ff4444",
        Status.PROCESSING: "#ffaa00",
    }
    STATUS_TEXT = {
        Status.IDLE: "IDLE",
        Status.RECORDING: "REC",
        Status.PROCESSING: "...",
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self._queue: queue.Queue = queue.Queue()
        self._setup_window()
        self._create_widgets()
        # Defer Win32 tweaks until the window is mapped
        self.root.after(100, self._prevent_focus_steal)
        self._poll_queue()

    # -- window setup -------------------------------------------------------

    def _setup_window(self):
        self.root.title("Voice Type")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.88)
        self.root.configure(bg=self.BG)

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        w, h = 820, 88
        x = (screen_w - w) // 2
        y = screen_h - h - 60  # just above the taskbar
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _create_widgets(self):
        # Top row: status dot + label, mode label
        top = tk.Frame(self.root, bg=self.BG)
        top.pack(fill="x", padx=12, pady=(6, 0))

        self.status_dot = tk.Label(
            top, text="\u25cf", fg=self.STATUS_COLORS[Status.IDLE],
            bg=self.BG, font=("Segoe UI", 9),
        )
        self.status_dot.pack(side="left")

        self.status_label = tk.Label(
            top, text="IDLE", fg=self.FG_DIM,
            bg=self.BG, font=("Segoe UI", 9),
        )
        self.status_label.pack(side="left", padx=(4, 0))

        self.mode_label = tk.Label(
            top, text="INPUT", fg=self.FG_DIM,
            bg=self.BG, font=("Segoe UI", 9),
        )
        self.mode_label.pack(side="right")

        # Main transcription text
        self.text_label = tk.Label(
            self.root,
            text="Ready \u2014 Ctrl+Shift+Space to dictate",
            fg=self.FG_TEXT, bg=self.BG,
            font=("Consolas", 11),
            wraplength=796, justify="left", anchor="w",
        )
        self.text_label.pack(fill="both", expand=True, padx=12, pady=(2, 8))

    def _prevent_focus_steal(self):
        """Set Win32 extended styles so the overlay never steals focus."""
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())

            GWL_EXSTYLE = -20
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOOLWINDOW = 0x00000080

            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

            SWP_NOACTIVATE = 0x0010
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_FRAMECHANGED = 0x0020
            ctypes.windll.user32.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
        except Exception as exc:
            print(f"[overlay] Could not set WS_EX_NOACTIVATE: {exc}")

    # -- thread-safe updates ------------------------------------------------

    def _poll_queue(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "update":
                    _, text, status, mode = msg
                    if text is not None:
                        self.text_label.config(text=text)
                    if status is not None:
                        self.status_dot.config(fg=self.STATUS_COLORS[status])
                        self.status_label.config(text=self.STATUS_TEXT[status])
                    if mode is not None:
                        self.mode_label.config(text=mode.value.upper())
                elif kind == "delayed_update":
                    _, delay_ms, text, status, mode = msg
                    self.root.after(delay_ms, lambda t=text, s=status, m=mode:
                        self.update(t, s, m))
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def update(self, text=None, status=None, mode=None):
        """Thread-safe — can be called from any thread."""
        self._queue.put(("update", text, status, mode))

    def update_delayed(self, delay_ms, text=None, status=None, mode=None):
        """Thread-safe delayed update — schedules via the main thread."""
        self._queue.put(("delayed_update", delay_ms, text, status, mode))


# ---------------------------------------------------------------------------
# Output Handlers
# ---------------------------------------------------------------------------

def _setup_clipboard_ctypes():
    """Declare proper 64-bit return/arg types for Win32 clipboard functions.

    Without this, ctypes assumes all functions return c_int (32-bit),
    which truncates 64-bit pointers on Windows x64 — causing access
    violations when writing to the allocated memory.
    """
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    user32.OpenClipboard.restype = ctypes.c_bool
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.CloseClipboard.restype = ctypes.c_bool
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]


_clipboard_types_set = False


def paste_to_active_window(text: str):
    """Copy *text* to the Windows clipboard and simulate Ctrl+V.

    Uses the Win32 clipboard API via ctypes so it can be called safely
    from any thread (unlike tkinter clipboard methods).
    """
    global _clipboard_types_set
    if not _clipboard_types_set:
        _setup_clipboard_ctypes()
        _clipboard_types_set = True

    import keyboard as kb

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    # Encode as null-terminated UTF-16LE (what Windows expects)
    data = text.encode("utf-16-le") + b"\x00\x00"

    if not user32.OpenClipboard(None):
        print("[paste] Could not open clipboard, retrying...")
        time.sleep(0.1)
        if not user32.OpenClipboard(None):
            print("[paste] Failed to open clipboard")
            return

    try:
        user32.EmptyClipboard()
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h_mem:
            print("[paste] GlobalAlloc failed")
            return
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            print("[paste] GlobalLock failed")
            return
        ctypes.memmove(p_mem, data, len(data))
        kernel32.GlobalUnlock(h_mem)
        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
    finally:
        user32.CloseClipboard()

    time.sleep(0.05)
    kb.send("ctrl+v")


def append_to_scratchpad(text: str, path: Path):
    """Append a timestamped line to the scratchpad file."""
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class VoiceType:
    """Wires together the overlay, recorder, hotkeys, and output handlers."""

    QUIT_HOTKEY = "ctrl+shift+q"

    def __init__(self, args: argparse.Namespace):
        self.mode = Mode(args.mode)
        self.hotkey: str = args.hotkey
        self.toggle_hotkey: str = args.toggle_hotkey
        self.model: str = args.model
        self.language: str = args.language
        self.device: str = args.device

        # Resolve scratchpad path relative to script dir (avoids slow
        # \\wsl$\ UNC paths when launched from WSL).
        sp = Path(args.scratchpad_file)
        self.scratchpad_path = sp if sp.is_absolute() else SCRIPT_DIR / sp

        self._is_recording = False
        self._is_processing = False
        self._lock = threading.Lock()

        # -- tkinter (must be on main thread) --------------------------------
        self.root = tk.Tk()
        self.overlay = Overlay(self.root)
        self.overlay.update(mode=self.mode)

        # -- RealtimeSTT (deferred to background thread for model loading) ---
        self.recorder = None
        self._recorder_ready = threading.Event()
        threading.Thread(target=self._init_recorder, daemon=True).start()

        # -- Hotkeys ---------------------------------------------------------
        self._register_hotkeys()

        # -- Graceful shutdown -----------------------------------------------
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

    # -- recorder setup -----------------------------------------------------

    def _init_recorder(self):
        from RealtimeSTT import AudioToTextRecorder

        self.overlay.update(text="Loading Whisper models\u2026")

        self.recorder = AudioToTextRecorder(
            model=self.model,
            language=self.language,
            device=self.device,
            # Realtime streaming for live display
            enable_realtime_transcription=True,
            realtime_model_type="tiny",
            realtime_processing_pause=0.2,
            # We control stop via hotkey, so set silence duration very high
            # to prevent auto-stop during pauses in speech.
            post_speech_silence_duration=60.0,
            # Callbacks
            on_realtime_transcription_update=self._on_realtime_update,
            on_recording_start=self._on_recording_start,
            on_recording_stop=self._on_recording_stop,
        )

        self._recorder_ready.set()
        self.overlay.update(
            text=f"Ready \u2014 {self.hotkey} to dictate",
            status=Status.IDLE,
        )
        print(f"[voice-type] Recorder ready  model={self.model}  device={self.device}")

    # -- RealtimeSTT callbacks (called from recorder threads) ----------------

    def _on_realtime_update(self, text: str):
        if text.strip():
            self.overlay.update(text=text.strip())

    def _on_recording_start(self):
        self.overlay.update(status=Status.RECORDING)

    def _on_recording_stop(self):
        self.overlay.update(status=Status.PROCESSING)

    def _on_final_text(self, text: str):
        """Called from the recorder.text() background thread."""
        text = text.strip()
        with self._lock:
            self._is_processing = False

        if not text:
            self.overlay.update(
                text=f"(no speech detected) \u2014 {self.hotkey} to dictate",
                status=Status.IDLE,
            )
            return

        if self.mode == Mode.INPUT:
            paste_to_active_window(text)
            self.overlay.update(text=text, status=Status.IDLE)
            # Reset to ready message after a delay.  Uses the overlay's
            # thread-safe delayed update instead of root.after() directly
            # (which is NOT safe to call from a non-main thread).
            self.overlay.update_delayed(
                3000,
                text=f"Ready \u2014 {self.hotkey} to dictate",
            )
        else:
            append_to_scratchpad(text, self.scratchpad_path)
            self.overlay.update(text=text, status=Status.IDLE)
            print(f"[scratchpad] {text}")

    # -- hotkey handlers ----------------------------------------------------

    def _start_recording(self):
        """Called in a background thread — safe to block."""
        if not self._recorder_ready.is_set():
            self.overlay.update(text="Still loading models, please wait\u2026")
            with self._lock:
                self._is_recording = False
            return

        self.overlay.update(text="Listening\u2026", status=Status.RECORDING)
        self.recorder.start()

    def _stop_recording(self):
        """Called in a background thread — safe to block."""
        self.overlay.update(status=Status.PROCESSING)
        self.recorder.stop()
        self.recorder.text(self._on_final_text)

    def _toggle_recording(self):
        """Hotkey callback — must return FAST or Windows kills our hook.

        Only touches the lock and fires off a background thread; all
        slow work (recorder.start / stop / text) happens there.
        """
        with self._lock:
            if self._is_processing:
                return
            if self._is_recording:
                self._is_recording = False
                self._is_processing = True
                threading.Thread(target=self._stop_recording, daemon=True).start()
            else:
                self._is_recording = True
                threading.Thread(target=self._start_recording, daemon=True).start()

    def _toggle_mode(self):
        if self.mode == Mode.INPUT:
            self.mode = Mode.SCRATCHPAD
        else:
            self.mode = Mode.INPUT
        self.overlay.update(mode=self.mode)
        print(f"[voice-type] Mode switched to {self.mode.value}")

    def _register_hotkeys(self):
        import keyboard as kb

        kb.add_hotkey(self.hotkey, self._toggle_recording, suppress=False)
        kb.add_hotkey(self.toggle_hotkey, self._toggle_mode, suppress=False)
        kb.add_hotkey(self.QUIT_HOTKEY, self._request_quit, suppress=False)

        print(f"[voice-type] Hotkeys registered:")
        print(f"  {self.hotkey}  \u2014  toggle recording")
        print(f"  {self.toggle_hotkey}  \u2014  switch mode (input/scratchpad)")
        print(f"  {self.QUIT_HOTKEY}  \u2014  quit")

    # -- lifecycle ----------------------------------------------------------

    def _request_quit(self):
        """Called from the keyboard listener thread — schedule shutdown
        on the main thread via the tkinter event loop."""
        self.overlay.update(text="Shutting down\u2026")
        # root.after is the one tkinter method that IS safe from other
        # threads on Windows (it posts to the Tcl event queue).
        self.root.after(0, self.shutdown)

    def run(self):
        """Start the tkinter main loop (blocks)."""
        print("[voice-type] Starting\u2026")
        self.root.mainloop()

    def shutdown(self):
        """Clean up and exit."""
        print("[voice-type] Shutting down\u2026")
        import keyboard as kb
        try:
            kb.unhook_all()
        except Exception:
            pass

        if self.recorder:
            try:
                if self._is_recording:
                    self.recorder.stop()
                self.recorder.shutdown()
            except Exception:
                pass

        try:
            self.root.destroy()
        except Exception:
            pass

        # RealtimeSTT spawns daemon threads and child processes that can
        # keep the process alive after mainloop exits.  os._exit is the
        # only reliable way to kill everything from a Windows process
        # launched via WSL interop (where Ctrl+C / SIGINT don't work).
        os._exit(0)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Voice Type \u2014 Whisper-powered voice dictation",
    )
    p.add_argument(
        "--mode", choices=["input", "scratchpad"], default="input",
        help="Starting mode: 'input' pastes to active window, "
             "'scratchpad' appends to a file (default: input)",
    )
    p.add_argument(
        "--hotkey", default="ctrl+shift+space",
        help="Global hotkey to toggle recording (default: ctrl+shift+space)",
    )
    p.add_argument(
        "--toggle-hotkey", default="ctrl+shift+s",
        help="Hotkey to switch between input/scratchpad mode (default: ctrl+shift+s)",
    )
    p.add_argument(
        "--model", default="base",
        help="Whisper model for final transcription (default: base)",
    )
    p.add_argument(
        "--language", default="en",
        help="Transcription language (default: en)",
    )
    p.add_argument(
        "--scratchpad-file", default="scratchpad.txt",
        help="Path for scratchpad output (default: scratchpad.txt)",
    )
    p.add_argument(
        "--device", default="cpu", choices=["cpu", "cuda"],
        help="Inference device (default: cpu)",
    )
    return p.parse_args()


def main():
    if platform.system() != "Windows":
        print("Error: voice_type.py must be run with Windows Python (python.exe).")
        print("From WSL, run:  python.exe voice_type.py")
        raise SystemExit(1)

    from dotenv import load_dotenv
    load_dotenv(SCRIPT_DIR / ".env")

    args = parse_args()
    app = VoiceType(args)
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()


if __name__ == "__main__":
    main()
