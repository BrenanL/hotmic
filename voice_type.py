"""HotMic — Whisper-powered voice dictation for Windows.

A lightweight overlay that captures speech via hotkey, shows live
transcription, and optionally auto-pastes into the active window.
All transcriptions are saved to history.txt and shown in the overlay.

Must be run with Windows Python (python.exe), not WSL Python.
"""

import argparse
import ctypes
import datetime
import os
import platform
import queue
import re
import threading
import time
import tkinter as tk
from collections import deque
from enum import Enum, auto
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HISTORY_LINE_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (.+)$")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Status(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


# ---------------------------------------------------------------------------
# Win32 helpers
# ---------------------------------------------------------------------------

def _apply_no_activate(hwnd):
    """Set WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW on a window handle."""
    GWL_EXSTYLE = -20
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOOLWINDOW = 0x00000080
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    SWP = 0x0010 | 0x0002 | 0x0001 | 0x0020  # NOACTIVATE|NOMOVE|NOSIZE|FRAMECHANGED
    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP)


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to the Windows clipboard via Win32 API (thread-safe)."""
    global _clipboard_types_set
    if not _clipboard_types_set:
        _setup_clipboard_ctypes()
        _clipboard_types_set = True

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    data = text.encode("utf-16-le") + b"\x00\x00"

    if not user32.OpenClipboard(None):
        time.sleep(0.1)
        if not user32.OpenClipboard(None):
            print("[clipboard] Failed to open clipboard")
            return False
    try:
        user32.EmptyClipboard()
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h_mem:
            return False
        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            return False
        ctypes.memmove(p_mem, data, len(data))
        kernel32.GlobalUnlock(h_mem)
        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
    finally:
        user32.CloseClipboard()
    return True


def _setup_clipboard_ctypes():
    """Declare proper 64-bit return/arg types for Win32 clipboard functions."""
    k = ctypes.windll.kernel32
    u = ctypes.windll.user32
    k.GlobalAlloc.restype = ctypes.c_void_p
    k.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalLock.argtypes = [ctypes.c_void_p]
    k.GlobalUnlock.restype = ctypes.c_bool
    k.GlobalUnlock.argtypes = [ctypes.c_void_p]
    u.OpenClipboard.restype = ctypes.c_bool
    u.OpenClipboard.argtypes = [ctypes.c_void_p]
    u.CloseClipboard.restype = ctypes.c_bool
    u.EmptyClipboard.restype = ctypes.c_bool
    u.SetClipboardData.restype = ctypes.c_void_p
    u.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]


_clipboard_types_set = False


# ---------------------------------------------------------------------------
# History file
# ---------------------------------------------------------------------------

def append_to_history_file(text: str, path: Path):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")


def load_history_file(path: Path, max_items: int) -> list[tuple[str, str]]:
    """Load the last *max_items* entries from history.txt.

    Returns list of (display_timestamp, text) tuples.
    """
    if not path.exists():
        return []
    entries: list[tuple[str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = HISTORY_LINE_RE.match(line.rstrip("\n"))
            if m:
                # Show only HH:MM:SS in the overlay (date is in the file)
                display_ts = m.group(1).split(" ", 1)[1]
                entries.append((display_ts, m.group(2)))
    return entries[-max_items:]


# ---------------------------------------------------------------------------
# Mini Indicator
# ---------------------------------------------------------------------------

class MiniIndicator:
    """Tiny always-on-top dot in the top-right corner (shown when overlay hidden)."""

    SIZE = 28
    BG = "#1a1a2e"
    COLORS = {
        Status.IDLE: "#555555",
        Status.RECORDING: "#ff4444",
        Status.PROCESSING: "#ffaa00",
    }

    def __init__(self, root: tk.Tk):
        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.attributes("-alpha", 0.92)
        self._win.configure(bg=self.BG)

        x = self._win.winfo_screenwidth() - self.SIZE - 12
        self._win.geometry(f"{self.SIZE}x{self.SIZE}+{x}+12")

        self._dot = tk.Label(
            self._win, text="\u25cf", bg=self.BG,
            fg=self.COLORS[Status.IDLE], font=("Segoe UI", 12),
        )
        self._dot.pack(expand=True)
        self._win.withdraw()
        self._win.after(100, self._apply_styles)

    def _apply_styles(self):
        try:
            self._win.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self._win.winfo_id())
            _apply_no_activate(hwnd)
        except Exception:
            pass

    def show(self):
        self._win.deiconify()

    def hide(self):
        self._win.withdraw()

    def set_status(self, status: Status):
        self._dot.config(fg=self.COLORS[status])


# ---------------------------------------------------------------------------
# Overlay Window
# ---------------------------------------------------------------------------

class Overlay:
    """Transparent always-on-top overlay for live transcription display."""

    BG = "#1a1a2e"
    BG_FLASH = "#2a2a4e"
    FG_TEXT = "#e0e0e0"
    FG_DIM = "#888888"
    FG_HISTORY = "#aaaaaa"
    FG_BTN = "#6688cc"
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

    def __init__(self, root: tk.Tk, max_history: int):
        self.root = root
        self._queue: queue.Queue = queue.Queue()
        self._history: deque[tuple[str, str]] = deque(maxlen=max_history)
        self._visible = True
        self._current_status = Status.IDLE

        self._setup_window()
        self._create_widgets()
        self._make_draggable()
        self.mini = MiniIndicator(root)

        self.root.after(100, self._prevent_focus_steal)
        self._poll_queue()

    # -- window setup -------------------------------------------------------

    def _setup_window(self):
        self.root.title("HotMic")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.88)
        self.root.configure(bg=self.BG)

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        w, h = 820, 160
        x = (screen_w - w) // 2
        y = screen_h - h - 60
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _create_widgets(self):
        # -- top bar --
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

        self.paste_label = tk.Label(
            top, text="PASTE ON", fg="#88cc88",
            bg=self.BG, font=("Segoe UI", 9),
        )
        self.paste_label.pack(side="left", padx=(10, 0))

        # Right-side buttons (packed right-to-left)
        self._help_btn = tk.Label(
            top, text="?", fg=self.FG_DIM, bg=self.BG,
            font=("Segoe UI", 9, "bold"), cursor="hand2",
        )
        self._help_btn.pack(side="right", padx=(8, 0))
        self._help_btn.bind("<Enter>", self._show_hotkey_tooltip)
        self._help_btn.bind("<Leave>", self._hide_hotkey_tooltip)
        self._tooltip = None

        for text, cmd in [
            ("[Clear]", self._on_clear_click),
            ("[Copy All]", self._on_copy_all_click),
        ]:
            btn = tk.Label(
                top, text=text, fg=self.FG_BTN, bg=self.BG,
                font=("Segoe UI", 9), cursor="hand2",
            )
            btn.pack(side="right", padx=(8, 0))
            btn.bind("<Button-1>", lambda e, c=cmd: c())

        # -- text area --
        self.text_area = tk.Text(
            self.root, bg=self.BG, fg=self.FG_TEXT,
            font=("Consolas", 10), wrap="word",
            borderwidth=0, highlightthickness=0,
            padx=12, pady=4,
            state="disabled",
            cursor="arrow",
        )
        self.text_area.pack(fill="both", expand=True, padx=0, pady=(2, 8))

        # Tag styles
        self.text_area.tag_configure("history", foreground=self.FG_HISTORY)
        self.text_area.tag_configure("live", foreground=self.FG_TEXT)
        self.text_area.tag_configure(
            "timestamp", foreground="#666688", font=("Consolas", 8),
        )
        self.text_area.tag_configure("flash_bg", background=self.BG_FLASH)

    def _make_draggable(self):
        self._drag_x = 0
        self._drag_y = 0

        def on_press(e):
            self._drag_x = e.x
            self._drag_y = e.y

        def on_drag(e):
            x = self.root.winfo_x() + (e.x - self._drag_x)
            y = self.root.winfo_y() + (e.y - self._drag_y)
            self.root.geometry(f"+{x}+{y}")

        self.root.bind("<ButtonPress-1>", on_press)
        self.root.bind("<B1-Motion>", on_drag)

    def _prevent_focus_steal(self):
        try:
            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            _apply_no_activate(hwnd)
        except Exception as exc:
            print(f"[overlay] Could not set WS_EX_NOACTIVATE: {exc}")

    # -- hotkey tooltip -----------------------------------------------------

    def _show_hotkey_tooltip(self, event):
        if self._tooltip:
            return
        x = self._help_btn.winfo_rootx() - 200
        y = self._help_btn.winfo_rooty() - 110
        self._tooltip = tw = tk.Toplevel(self.root)
        tw.overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.configure(bg="#2a2a3e")
        tw.geometry(f"+{x}+{y}")
        lines = [
            ("Ctrl+Alt+Space", "Toggle recording"),
            ("Ctrl+Alt+P", "Toggle auto-paste"),
            ("Ctrl+Alt+C", "Copy all history"),
            ("Ctrl+Alt+H", "Hide / show overlay"),
            ("Ctrl+Alt+Q", "Quit"),
        ]
        for key, desc in lines:
            row = tk.Frame(tw, bg="#2a2a3e")
            row.pack(fill="x", padx=8, pady=1)
            tk.Label(
                row, text=key, fg="#aaaacc", bg="#2a2a3e",
                font=("Consolas", 9), anchor="w", width=18,
            ).pack(side="left")
            tk.Label(
                row, text=desc, fg="#888899", bg="#2a2a3e",
                font=("Segoe UI", 9), anchor="w",
            ).pack(side="left")

    def _hide_hotkey_tooltip(self, event):
        if self._tooltip:
            self._tooltip.destroy()
            self._tooltip = None

    # -- copy / clear -------------------------------------------------------

    def _copy_entry(self, index: int):
        """Copy a specific history entry by index and flash it."""
        if 0 <= index < len(self._history):
            text = self._history[index][1]
            if _copy_to_clipboard(text):
                self._flash_entry(index)

    def _flash_entry(self, index: int):
        """Briefly highlight a history entry to confirm the copy."""
        tag = f"entry_{index}"
        self.text_area.tag_add("flash_bg", *self.text_area.tag_ranges(tag))
        self.root.after(300, lambda: self.text_area.tag_remove(
            "flash_bg", "1.0", "end"))

    def _on_copy_all_click(self):
        """Copy all visible history entries, newline-separated."""
        if self._history:
            combined = "\n".join(entry for _, entry in self._history)
            if _copy_to_clipboard(combined):
                self._show_status_message("Copied all!")

    def _on_clear_click(self):
        """Clear the overlay display (not the file)."""
        self._history.clear()
        self._render_history()

    def copy_all(self):
        """Copy all visible history — called from hotkey via queue."""
        self._on_copy_all_click()

    def _show_status_message(self, msg: str):
        """Briefly show a message in the status label."""
        old = self.status_label.cget("text")
        self.status_label.config(text=msg, fg="#88cc88")
        self.root.after(1500, lambda: self.status_label.config(
            text=self.STATUS_TEXT.get(self._current_status, "IDLE"),
            fg=self.FG_DIM,
        ))

    # -- auto-paste indicator -----------------------------------------------

    def set_auto_paste(self, on: bool):
        if on:
            self.paste_label.config(text="PASTE ON", fg="#88cc88")
        else:
            self.paste_label.config(text="PASTE OFF", fg="#cc8888")

    # -- visibility ---------------------------------------------------------

    def toggle_visibility(self):
        if self._visible:
            self.root.withdraw()
            self.mini.show()
            self.mini.set_status(self._current_status)
            self._visible = False
        else:
            self.root.deiconify()
            self.mini.hide()
            self._visible = True

    # -- history management -------------------------------------------------

    def add_history(self, text: str, ts: str | None = None):
        if ts is None:
            ts = datetime.datetime.now().strftime("%H:%M:%S")
        self._history.append((ts, text))

    def seed_history(self, entries: list[tuple[str, str]]):
        """Load entries from a previous session into the display."""
        for ts, text in entries:
            self._history.append((ts, text))
        self._render_history()

    def _render_history(self):
        """Redraw the text area with current history + click-to-copy tags."""
        self.text_area.config(state="normal")
        self.text_area.delete("1.0", "end")

        if not self._history:
            self.text_area.insert("end",
                                  "Ready \u2014 Ctrl+Alt+Space to dictate", "live")
            self.text_area.config(state="disabled")
            return

        for i, (ts, entry) in enumerate(self._history):
            if i > 0:
                self.text_area.insert("end", "\n")

            tag_name = f"entry_{i}"
            start = self.text_area.index("end-1c")

            self.text_area.insert("end", f"[{ts}] ", "timestamp")
            is_latest = (i == len(self._history) - 1)
            style_tag = "live" if is_latest else "history"
            self.text_area.insert("end", entry, style_tag)

            end = self.text_area.index("end-1c")

            # Create per-entry tag spanning timestamp + text
            self.text_area.tag_add(tag_name, start, end)
            self.text_area.tag_bind(
                tag_name, "<Button-1>",
                lambda e, idx=i: self._copy_entry(idx),
            )

        self.text_area.see("end")
        self.text_area.config(state="disabled")

    # -- thread-safe updates ------------------------------------------------

    def _poll_queue(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "update":
                    _, text, status, auto_paste = msg
                    if text is not None:
                        self.text_area.config(state="normal")
                        self.text_area.delete("1.0", "end")
                        self.text_area.insert("end", text, "live")
                        self.text_area.config(state="disabled")
                    if status is not None:
                        self._current_status = status
                        self.status_dot.config(fg=self.STATUS_COLORS[status])
                        self.status_label.config(text=self.STATUS_TEXT[status])
                        self.mini.set_status(status)
                    if auto_paste is not None:
                        self.set_auto_paste(auto_paste)
                elif kind == "add_history":
                    _, text = msg
                    self.add_history(text)
                    self._render_history()
                elif kind == "copy_all":
                    self._on_copy_all_click()
                elif kind == "clear":
                    self._on_clear_click()
                elif kind == "delayed_update":
                    _, delay_ms, text, status, ap = msg
                    self.root.after(delay_ms, lambda t=text, s=status, a=ap:
                        self.update(t, s, a))
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def update(self, text=None, status=None, auto_paste=None):
        """Thread-safe — can be called from any thread."""
        self._queue.put(("update", text, status, auto_paste))

    def update_delayed(self, delay_ms, text=None, status=None, auto_paste=None):
        self._queue.put(("delayed_update", delay_ms, text, status, auto_paste))

    def push_history(self, text: str):
        """Thread-safe — add a transcription to history and redraw."""
        self._queue.put(("add_history", text))

    def request_copy_all(self):
        """Thread-safe — copy all from hotkey."""
        self._queue.put(("copy_all",))

    def request_clear(self):
        """Thread-safe — clear from hotkey."""
        self._queue.put(("clear",))


# ---------------------------------------------------------------------------
# Output Handlers
# ---------------------------------------------------------------------------

def paste_to_active_window(text: str):
    """Copy text to clipboard and simulate Ctrl+V."""
    import keyboard as kb
    if _copy_to_clipboard(text):
        time.sleep(0.05)
        kb.send("ctrl+v")


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------

class HotMic:
    """Wires together the overlay, recorder, hotkeys, and output handlers."""

    QUIT_HOTKEY = "ctrl+alt+q"
    COPY_ALL_HOTKEY = "ctrl+alt+c"
    HIDE_HOTKEY = "ctrl+alt+h"
    PASTE_TOGGLE_HOTKEY = "ctrl+alt+p"

    def __init__(self, args: argparse.Namespace):
        self.auto_paste: bool = args.auto_paste
        self.hotkey: str = args.hotkey
        self.model: str = args.model
        self.language: str = args.language
        self.device: str = args.device

        hp = Path(args.history_file)
        self.history_path = hp if hp.is_absolute() else SCRIPT_DIR / hp

        self._is_recording = False
        self._is_processing = False
        self._lock = threading.Lock()

        # -- tkinter ---------------------------------------------------------
        self.root = tk.Tk()
        self.overlay = Overlay(self.root, max_history=args.max_history)
        self.overlay.update(auto_paste=self.auto_paste)

        # Optionally load previous session's history
        if args.load_history:
            entries = load_history_file(self.history_path, args.max_history)
            if entries:
                self.overlay.seed_history(entries)
                print(f"[hotmic] Loaded {len(entries)} history entries")

        # -- RealtimeSTT -----------------------------------------------------
        self.recorder = None
        self._recorder_ready = threading.Event()
        threading.Thread(target=self._init_recorder, daemon=True).start()

        # -- Hotkeys ---------------------------------------------------------
        self._register_hotkeys()
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)

    # -- recorder setup -----------------------------------------------------

    def _init_recorder(self):
        from RealtimeSTT import AudioToTextRecorder

        self.overlay.update(text="Loading Whisper models\u2026")

        self.recorder = AudioToTextRecorder(
            model=self.model,
            language=self.language,
            device=self.device,
            enable_realtime_transcription=True,
            realtime_model_type="tiny",
            realtime_processing_pause=0.2,
            post_speech_silence_duration=60.0,
            on_realtime_transcription_update=self._on_realtime_update,
            on_recording_start=self._on_recording_start,
            on_recording_stop=self._on_recording_stop,
        )

        self._recorder_ready.set()
        self.overlay.update(
            text=f"Ready \u2014 {self.hotkey} to dictate",
            status=Status.IDLE,
        )
        print(f"[hotmic] Recorder ready  model={self.model}  device={self.device}")

    # -- RealtimeSTT callbacks ----------------------------------------------

    def _on_realtime_update(self, text: str):
        if text.strip():
            self.overlay.update(text=text.strip())

    def _on_recording_start(self):
        self.overlay.update(status=Status.RECORDING)

    def _on_recording_stop(self):
        self.overlay.update(status=Status.PROCESSING)

    def _on_final_text(self, text: str):
        text = text.strip()
        with self._lock:
            self._is_processing = False

        if not text:
            self.overlay.update(
                text=f"(no speech detected) \u2014 {self.hotkey} to dictate",
                status=Status.IDLE,
            )
            return

        # Always save to history (file + overlay)
        append_to_history_file(text, self.history_path)
        self.overlay.push_history(text)
        self.overlay.update(status=Status.IDLE)

        if self.auto_paste:
            paste_to_active_window(text)

    # -- hotkey handlers ----------------------------------------------------

    def _start_recording(self):
        if not self._recorder_ready.is_set():
            self.overlay.update(text="Still loading models, please wait\u2026")
            with self._lock:
                self._is_recording = False
            return
        self.overlay.update(text="Listening\u2026", status=Status.RECORDING)
        self.recorder.start()

    def _stop_recording(self):
        self.overlay.update(status=Status.PROCESSING)
        self.recorder.stop()
        self.recorder.text(self._on_final_text)

    def _toggle_recording(self):
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

    def _toggle_auto_paste(self):
        self.auto_paste = not self.auto_paste
        self.overlay.update(auto_paste=self.auto_paste)
        state = "on" if self.auto_paste else "off"
        print(f"[hotmic] Auto-paste {state}")

    def _copy_all(self):
        self.overlay.request_copy_all()

    def _toggle_overlay(self):
        self.overlay.toggle_visibility()

    def _register_hotkeys(self):
        import keyboard as kb

        kb.add_hotkey(self.hotkey, self._toggle_recording, suppress=True)
        kb.add_hotkey(self.PASTE_TOGGLE_HOTKEY, self._toggle_auto_paste, suppress=True)
        kb.add_hotkey(self.COPY_ALL_HOTKEY, self._copy_all, suppress=True)
        kb.add_hotkey(self.HIDE_HOTKEY, self._toggle_overlay, suppress=True)
        kb.add_hotkey(self.QUIT_HOTKEY, self._request_quit, suppress=True)

        print("[hotmic] Hotkeys:")
        print(f"  {self.hotkey}  \u2014  toggle recording")
        print(f"  {self.PASTE_TOGGLE_HOTKEY}  \u2014  toggle auto-paste")
        print(f"  {self.COPY_ALL_HOTKEY}  \u2014  copy all history to clipboard")
        print(f"  {self.HIDE_HOTKEY}  \u2014  hide/show overlay")
        print(f"  {self.QUIT_HOTKEY}  \u2014  quit")

    # -- lifecycle ----------------------------------------------------------

    def _request_quit(self):
        self.overlay.update(text="Shutting down\u2026")
        self.root.after(0, self.shutdown)

    def run(self):
        print("[hotmic] Starting\u2026")
        self.root.mainloop()

    def shutdown(self):
        print("[hotmic] Shutting down\u2026")
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
        os._exit(0)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load config.toml from the script directory, returning a flat dict."""
    config_path = SCRIPT_DIR / "config.toml"
    if not config_path.exists():
        return {}
    config = {}
    with open(config_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"')
            # Parse booleans and integers
            if val.lower() == "true":
                val = True
            elif val.lower() == "false":
                val = False
            else:
                try:
                    val = int(val)
                except ValueError:
                    pass
            config[key] = val
    return config


def parse_args() -> argparse.Namespace:
    cfg = _load_config()

    p = argparse.ArgumentParser(
        description="HotMic \u2014 Whisper-powered voice dictation",
    )
    p.add_argument(
        "--hotkey", default=cfg.get("hotkey", "ctrl+alt+space"),
        help="Global hotkey to toggle recording",
    )
    p.add_argument(
        "--model", default=cfg.get("model", "base"),
        help="Whisper model for final transcription",
    )
    p.add_argument(
        "--language", default=cfg.get("language", "en"),
        help="Transcription language",
    )
    p.add_argument(
        "--history-file", default=cfg.get("history-file", "history.txt"),
        help="Path for history log",
    )
    p.add_argument(
        "--max-history", type=int, default=cfg.get("max-history", 50),
        help="Max history entries to display in overlay",
    )
    p.add_argument(
        "--load-history", action="store_true",
        default=cfg.get("load-history", False),
        help="Load previous session's history into overlay on launch",
    )
    p.add_argument(
        "--no-auto-paste", action="store_true",
        default=not cfg.get("auto-paste", True),
        help="Start with auto-paste disabled",
    )
    p.add_argument(
        "--device", default=cfg.get("device", "cpu"), choices=["cpu", "cuda"],
        help="Inference device",
    )
    args = p.parse_args()
    args.auto_paste = not args.no_auto_paste
    return args


def main():
    if platform.system() != "Windows":
        print("Error: HotMic must be run with Windows Python (python.exe).")
        print("From WSL, run:  ./hotmic")
        raise SystemExit(1)

    # Ensure CWD is the project directory — Start Menu shortcuts default to
    # system32, which causes permission errors for log files and model caches.
    os.chdir(SCRIPT_DIR)

    args = parse_args()
    app = HotMic(args)
    try:
        app.run()
    except KeyboardInterrupt:
        app.shutdown()


if __name__ == "__main__":
    main()
