"""
GLaDOS Voice Chat — tkinter GUI.
Run this file (or use run.bat) to start the application.
"""

import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
SETTINGS_FILE = SCRIPT_DIR / "settings.json"
REQUIREMENTS_FILE = SCRIPT_DIR / "requirements.txt"
TTS_DIR = SCRIPT_DIR / "GLaDOS-TTS"

# ---------------------------------------------------------------------------
# Try importing the engine (requires numpy, torch, sounddevice, GLaDOS-TTS…)
# If anything is missing, we show the setup dialog before proceeding.
# ---------------------------------------------------------------------------
try:
    from glados_engine import GladosEngine, get_defaults
    _DEPS_READY = True
except ImportError:
    GladosEngine = None
    get_defaults = None
    _DEPS_READY = False

# ---------------------------------------------------------------------------
# Theme colours  (Portal / GLaDOS aesthetic)
# ---------------------------------------------------------------------------
BG           = "#0d1117"
BG2          = "#161b22"
BG3          = "#21262d"
TEXT         = "#e6edf3"
TEXT_DIM     = "#8b949e"
ACCENT       = "#ff6600"
ACCENT_HOVER = "#ff8833"
USER_CLR     = "#58a6ff"
GLADOS_CLR   = "#ff7b00"
SUCCESS      = "#3fb950"
WARNING      = "#d29922"
ERROR        = "#f85149"
BORDER       = "#30363d"
BUBBLE_USER  = "#1a56db"
BUBBLE_GLADOS = "#2d333b"
METER_BG     = "#1a1e24"
METER_IDLE   = "#2ea043"
METER_SPEECH = "#ff6600"


# ===================================================================
# Settings helpers
# ===================================================================
def load_settings() -> dict:
    defaults = get_defaults()
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
            # Merge saved over defaults so new keys still appear
            for section in defaults:
                if section in saved:
                    defaults[section].update(saved[section])
            return defaults
        except Exception:
            pass
    return defaults


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


# ===================================================================
# Dependency setup dialog (shown when packages or TTS files are missing)
# ===================================================================
class SetupDialog(tk.Toplevel):
    """Installs pip packages and GLaDOS TTS models with live progress."""

    def __init__(self, parent, need_pkgs=True, need_tts=True):
        super().__init__(parent)
        self.success = False
        self._need_pkgs = need_pkgs
        self._need_tts = need_tts
        self._installing = False

        self.title("GLaDOS — Setup Required")
        self.geometry("580x420")
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.resizable(False, False)

        self.update_idletasks()
        x = (self.winfo_screenwidth() - 580) // 2
        y = (self.winfo_screenheight() - 420) // 2
        self.geometry(f"+{x}+{y}")

        # ---- Title ----
        tk.Label(self, text="Setup Required", font=("Consolas", 18, "bold"),
                 fg=ACCENT, bg=BG).pack(pady=(20, 8))

        # ---- What needs to happen ----
        steps = []
        if need_pkgs:
            steps.append("Install Python packages (torch, transformers, etc.)")
        if need_tts:
            steps.append("Download GLaDOS TTS voice models (~120 MB)")
        desc = "\n".join(f"  \u2022 {s}" for s in steps)
        tk.Label(self, text=desc, font=("Consolas", 10), fg=TEXT, bg=BG,
                 justify=tk.LEFT, anchor=tk.W).pack(fill=tk.X, padx=40, pady=(0, 14))

        # ---- Install button ----
        self.btn_install = tk.Button(
            self, text="Install", command=self._start,
            font=("Consolas", 12, "bold"), bg=ACCENT, fg=BG,
            activebackground=ACCENT_HOVER, activeforeground=BG,
            relief=tk.FLAT, padx=20, pady=6, cursor="hand2", borderwidth=0,
        )
        self.btn_install.pack(pady=(0, 10))

        # ---- Status label ----
        self.status_label = tk.Label(self, text="", font=("Consolas", 9),
                                     fg=TEXT_DIM, bg=BG, anchor=tk.W)
        self.status_label.pack(fill=tk.X, padx=40)

        # ---- Log area ----
        self.log_area = scrolledtext.ScrolledText(
            self, height=10, bg=BG2, fg=TEXT_DIM, font=("Consolas", 8),
            relief=tk.FLAT, borderwidth=4, state=tk.DISABLED,
        )
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=20, pady=(6, 14))

    def _start(self):
        self.btn_install.configure(state=tk.DISABLED, text="Installing...")
        self._installing = True
        threading.Thread(target=self._setup_thread, daemon=True).start()

    def _setup_thread(self):
        try:
            if self._need_pkgs:
                self._set_status("Installing Python packages (this may take several minutes)...")
                self._run_cmd([
                    sys.executable, "-m", "pip", "install",
                    "-r", str(REQUIREMENTS_FILE),
                ])

            if self._need_tts:
                self._set_status("Downloading GLaDOS TTS models...")
                self._run_cmd([
                    sys.executable, str(SCRIPT_DIR / "setup_models.py"), "--skip-llm",
                ])

            self.success = True
            self._installing = False
            self._set_status("Setup complete! Restarting...")
            time.sleep(1)
            self.after(0, self.destroy)

        except Exception as e:
            self._installing = False
            self.after(0, lambda: self._on_error(str(e)))

    def _run_cmd(self, cmd):
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in proc.stdout:
            self._log(line.rstrip("\n"))
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"Command failed with exit code {proc.returncode}")

    def _log(self, text):
        def _do():
            self.log_area.configure(state=tk.NORMAL)
            self.log_area.insert(tk.END, text + "\n")
            self.log_area.configure(state=tk.DISABLED)
            self.log_area.see(tk.END)
        self.after(0, _do)

    def _set_status(self, text):
        self.after(0, lambda: self.status_label.configure(text=text, fg=TEXT_DIM))

    def _on_error(self, error):
        self.btn_install.configure(state=tk.NORMAL, text="Retry")
        self.status_label.configure(text=f"Error: {error}", fg=ERROR)

    def _on_close(self):
        if self._installing:
            return
        self.destroy()


# ===================================================================
# First-run model check
# ===================================================================
LLM_MODELS = [
    {
        "label": "Gemma 4 E2B",
        "desc": "Smaller and faster — good for low-VRAM GPUs",
        "size": "~5 GB",
        "id": "google/gemma-4-E2B-it",
    },
    {
        "label": "Gemma 4 E4B",
        "desc": "More capable — recommended with 8+ GB VRAM",
        "size": "~9 GB",
        "id": "google/gemma-4-E4B-it",
    },
]


def _is_model_cached(model_id: str) -> bool:
    """Check if a HuggingFace model is already in the local cache."""
    try:
        from huggingface_hub import try_to_load_from_cache
        result = try_to_load_from_cache(model_id, "config.json")
        return isinstance(result, str)
    except Exception:
        return False


def _any_known_model_cached() -> bool:
    """Check if any of the offered models are already cached."""
    return any(_is_model_cached(m["id"]) for m in LLM_MODELS)


class ModelDownloadDialog(tk.Toplevel):
    """First-run dialog: pick and download a language model with progress."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_app = parent
        self.chosen_model = None
        self._downloading = False

        self.title("GLaDOS — First Time Setup")
        self.geometry("520x400")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.resizable(False, False)

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 520) // 2
        y = (self.winfo_screenheight() - 400) // 2
        self.geometry(f"+{x}+{y}")

        # ---- Title ----
        tk.Label(self, text="Welcome to GLaDOS", font=("Consolas", 18, "bold"),
                 fg=ACCENT, bg=BG).pack(pady=(24, 4))
        tk.Label(self, text="Select a language model to download.",
                 font=("Consolas", 11), fg=TEXT_DIM, bg=BG).pack(pady=(0, 16))

        # ---- Model choices ----
        self.model_var = tk.StringVar(value=LLM_MODELS[0]["id"])

        choice_frame = tk.Frame(self, bg=BG)
        choice_frame.pack(fill=tk.X, padx=30)

        for m in LLM_MODELS:
            f = tk.Frame(choice_frame, bg=BG2, padx=12, pady=8,
                         highlightbackground=BORDER, highlightthickness=1)
            f.pack(fill=tk.X, pady=4)
            tk.Radiobutton(
                f, text=f"{m['label']}  ({m['size']})",
                variable=self.model_var, value=m["id"],
                font=("Consolas", 11, "bold"), fg=TEXT, bg=BG2,
                selectcolor=BG3, activebackground=BG2, activeforeground=TEXT,
                anchor=tk.W,
            ).pack(anchor=tk.W)
            tk.Label(f, text=m["desc"], font=("Consolas", 9),
                     fg=TEXT_DIM, bg=BG2, anchor=tk.W).pack(anchor=tk.W, padx=(20, 0))

        # ---- Download button ----
        self.btn_download = tk.Button(
            self, text="Download", command=self._start_download,
            font=("Consolas", 12, "bold"), bg=ACCENT, fg=BG,
            activebackground=ACCENT_HOVER, activeforeground=BG,
            relief=tk.FLAT, padx=20, pady=6, cursor="hand2", borderwidth=0,
        )
        self.btn_download.pack(pady=(20, 10))

        # ---- Progress bar ----
        style = ttk.Style(self)
        style.configure("DL.Horizontal.TProgressbar",
                        troughcolor=BG3, background=ACCENT, thickness=20)
        self.progress = ttk.Progressbar(
            self, style="DL.Horizontal.TProgressbar",
            mode="determinate", maximum=100, length=440,
        )
        self.progress.pack(pady=(0, 4))

        # ---- Status label ----
        self.status_label = tk.Label(self, text="", font=("Consolas", 9),
                                     fg=TEXT_DIM, bg=BG, anchor=tk.W)
        self.status_label.pack(fill=tk.X, padx=40)

    # ---- download logic ----
    def _start_download(self):
        self.btn_download.configure(state=tk.DISABLED, text="Downloading...")
        self.status_label.configure(fg=TEXT_DIM)
        self._downloading = True
        model_id = self.model_var.get()
        threading.Thread(target=self._download_thread, args=(model_id,), daemon=True).start()

    def _download_thread(self, model_id):
        try:
            from huggingface_hub import HfApi, snapshot_download
            try:
                from huggingface_hub.constants import HF_HUB_CACHE
            except ImportError:
                HF_HUB_CACHE = str(Path.home() / ".cache" / "huggingface" / "hub")

            # Get total model size from the API
            self._set_status("Fetching model info...")
            api = HfApi()
            info = api.model_info(model_id)
            total_size = sum(s.size for s in info.siblings if s.size) or 1
            total_mb = total_size / (1024 * 1024)

            # Locate cache directory for this model
            cache_dir = Path(HF_HUB_CACHE) / f"models--{model_id.replace('/', '--')}"

            def get_cache_size():
                try:
                    return sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
                except Exception:
                    return 0

            initial_size = get_cache_size()

            # Start the actual download in a sub-thread
            done = threading.Event()
            dl_error = [None]

            def _do_download():
                try:
                    snapshot_download(model_id)
                except Exception as e:
                    dl_error[0] = e
                done.set()

            threading.Thread(target=_do_download, daemon=True).start()

            # Poll cache size for progress updates
            while not done.is_set():
                current = max(get_cache_size() - initial_size, 0)
                pct = min(current / total_size * 100, 99)
                mb = current / (1024 * 1024)
                self._set_status(f"Downloading... {mb:,.0f} / {total_mb:,.0f} MB")
                self._set_progress(pct)
                done.wait(0.5)

            if dl_error[0]:
                raise dl_error[0]

            self._set_progress(100)
            self._set_status("Download complete!")
            self.after(300, lambda: self._on_complete(model_id))

        except Exception as e:
            self.after(0, lambda: self._on_error(str(e)))

    def _set_status(self, text):
        self.after(0, lambda: self.status_label.configure(text=text))

    def _set_progress(self, pct):
        self.after(0, lambda: self.progress.configure(value=pct))

    def _on_complete(self, model_id):
        self._downloading = False
        self.chosen_model = model_id
        self.destroy()

    def _on_error(self, error):
        self._downloading = False
        self.btn_download.configure(state=tk.NORMAL, text="Retry Download")
        self.status_label.configure(text=f"Error: {error}", fg=ERROR)
        self.progress.configure(value=0)

    def _on_close(self):
        if self._downloading:
            return  # don't close mid-download
        self.destroy()  # chosen_model stays None → app will exit


# ===================================================================
# Main application
# ===================================================================
class GladosApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GLaDOS Voice Chat")
        self.geometry("780x700")
        self.minsize(600, 500)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # --- settings ---
        self.settings = load_settings()

        # --- engine (created but NOT initialized yet) ---
        self.engine = GladosEngine(
            self.settings,
            on_status=self._cb_status,
            on_message=self._cb_message,
            on_volume=self._cb_volume,
            on_error=self._cb_error,
        )

        # --- volume meter state ---
        self._meter_rms = 0.0
        self._meter_ambient = 0.0
        self._meter_threshold = 0.0
        self._meter_speech = False

        # --- build UI ---
        self._build_ui()
        self._apply_theme()

        # --- boot sequence (check model first) ---
        self._append_system("Initializing GLaDOS Voice Chat...")
        self.after(100, self._check_model)

    # ---------------------------------------------------------------- first-run model check
    def _check_model(self):
        """If the configured LLM isn't cached, show the download dialog first."""
        model_id = self.settings["llm"]["model"]
        if _is_model_cached(model_id):
            self._boot()
            return

        # First run — show model selection dialog
        dialog = ModelDownloadDialog(self)
        self.wait_window(dialog)

        if dialog.chosen_model:
            self.settings["llm"]["model"] = dialog.chosen_model
            self.engine.settings["llm"]["model"] = dialog.chosen_model
            save_settings(self.settings)
            self._boot()
        else:
            # User closed without downloading — exit
            self.destroy()

    # ---------------------------------------------------------------- boot
    def _boot(self):
        """Kick off model loading + calibration in background."""
        self._model_switching = False
        self._poll_active = True

        def _init_thread():
            import logging, traceback
            log = logging.getLogger("glados")
            try:
                self.engine.initialize()
                if self._model_switching:
                    return
                # Greeting
                greeting = self.settings["general"]["greeting"]
                self.engine.messages.append({"role": "assistant", "content": greeting})
                self._cb_message("assistant", greeting)
                self._cb_status("Speaking")
                try:
                    self.engine.speak(greeting)
                except Exception:
                    log.error("Greeting speak error:\n%s", traceback.format_exc())
                if self._model_switching:
                    return
                # Calibrate + start listening
                self.engine.calibrate()
                if self._model_switching:
                    return
                self._cb_status("Listening")
                # Start the audio poll loop on the main thread
                self.after(50, self._poll_audio)
            except Exception:
                log.error("Boot thread crashed:\n%s", traceback.format_exc())
        threading.Thread(target=_init_thread, daemon=True).start()
        # Start meter refresh
        self._refresh_meter()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        # ---- top bar ----
        top = tk.Frame(self, bg=BG)
        top.pack(fill=tk.X, padx=10, pady=(10, 0))

        tk.Label(top, text="GLaDOS Voice Chat", font=("Consolas", 16, "bold"),
                 fg=ACCENT, bg=BG).pack(side=tk.LEFT)

        btn_frame = tk.Frame(top, bg=BG)
        btn_frame.pack(side=tk.RIGHT)

        self.btn_clear = tk.Button(btn_frame, text="Clear Chat", command=self._clear_chat,
                                   **self._btn_style())
        self.btn_clear.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_settings = tk.Button(btn_frame, text="Settings", command=self._open_settings,
                                      **self._btn_style())
        self.btn_settings.pack(side=tk.LEFT)

        # ---- chat area (scrollable bubble list) ----
        chat_outer = tk.Frame(self, bg=BG2, relief=tk.FLAT)
        chat_outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        self._chat_canvas = tk.Canvas(chat_outer, bg=BG2, highlightthickness=0)
        chat_sb = ttk.Scrollbar(chat_outer, orient=tk.VERTICAL,
                                command=self._chat_canvas.yview)
        self._chat_frame = tk.Frame(self._chat_canvas, bg=BG2)
        self._chat_frame_id = self._chat_canvas.create_window(
            (0, 0), window=self._chat_frame, anchor=tk.NW)
        self._chat_frame.bind(
            "<Configure>",
            lambda e: self._chat_canvas.configure(
                scrollregion=self._chat_canvas.bbox("all")))
        self._chat_canvas.configure(yscrollcommand=chat_sb.set)
        self._chat_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        chat_sb.pack(side=tk.RIGHT, fill=tk.Y)

        # Keep inner frame as wide as canvas
        self._chat_canvas.bind("<Configure>", self._on_chat_resize)
        # Mousewheel scrolling
        self._chat_canvas.bind("<MouseWheel>", self._on_chat_mousewheel)
        self._chat_frame.bind("<MouseWheel>", self._on_chat_mousewheel)

        # Bubble tracking
        self._chat_bubbles: list[tuple] = []  # (row_frame, role, msg_ref | None)
        self._rewind_map: dict[int, tuple] = {}  # id(bubble) -> (msg_ref, row)

        # ---- volume meter ----
        meter_frame = tk.Frame(self, bg=BG)
        meter_frame.pack(fill=tk.X, padx=10)

        self.meter_canvas = tk.Canvas(meter_frame, height=22, bg=METER_BG,
                                       highlightthickness=1, highlightbackground=BORDER)
        self.meter_canvas.pack(fill=tk.X, side=tk.LEFT, expand=True)

        self.meter_label = tk.Label(meter_frame, text="", font=("Consolas", 9),
                                    fg=TEXT_DIM, bg=BG, width=28, anchor=tk.W)
        self.meter_label.pack(side=tk.RIGHT, padx=(8, 0))

        # ---- status bar ----
        status_frame = tk.Frame(self, bg=BG)
        status_frame.pack(fill=tk.X, padx=10, pady=(4, 0))

        self.status_dot = tk.Label(status_frame, text="\u25CF", font=("Consolas", 12),
                                   fg=TEXT_DIM, bg=BG)
        self.status_dot.pack(side=tk.LEFT)
        self.status_label = tk.Label(status_frame, text="Initializing...",
                                     font=("Consolas", 10), fg=TEXT_DIM, bg=BG, anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, padx=(4, 0))

        # mic toggle on the right side of status bar
        self.mic_on = tk.BooleanVar(value=self.settings["vad"]["enabled"])
        self.btn_mic = tk.Checkbutton(
            status_frame, text="Auto-Listen", variable=self.mic_on,
            command=self._toggle_mic, font=("Consolas", 10),
            fg=TEXT, bg=BG, selectcolor=BG3,
            activebackground=BG, activeforeground=TEXT,
        )
        self.btn_mic.pack(side=tk.RIGHT)

        self.btn_skip = tk.Button(
            status_frame, text="Skip Voice Response", command=self._skip_speech,
            font=("Consolas", 9, "bold"), bg=BG3, fg=TEXT_DIM,
            activebackground=BG2, activeforeground=TEXT,
            relief=tk.FLAT, padx=6, pady=1, cursor="hand2", borderwidth=0,
            state=tk.DISABLED,
        )
        self.btn_skip.pack(side=tk.RIGHT, padx=(0, 6))

        # ---- input bar ----
        input_frame = tk.Frame(self, bg=BG)
        input_frame.pack(fill=tk.X, padx=10, pady=(6, 10))

        self.entry = tk.Entry(
            input_frame, font=("Consolas", 12),
            bg=BG3, fg=TEXT, insertbackground=TEXT,
            relief=tk.FLAT, borderwidth=6,
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", self._on_send)

        self.btn_send = tk.Button(input_frame, text="Send", command=self._on_send,
                                  **self._btn_style())
        self.btn_send.pack(side=tk.RIGHT, padx=(6, 0))

    def _btn_style(self):
        return dict(
            font=("Consolas", 10, "bold"), bg=BG3, fg=TEXT,
            activebackground=ACCENT, activeforeground=BG,
            relief=tk.FLAT, padx=10, pady=4, cursor="hand2",
            borderwidth=0,
        )

    def _apply_theme(self):
        """Style the scrollbar via ttk."""
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Vertical.TScrollbar",
                        background=BG3, troughcolor=BG2,
                        arrowcolor=TEXT_DIM, borderwidth=0)

    # ---------------------------------------------------------------- chat helpers
    def _on_chat_resize(self, event):
        self._chat_canvas.itemconfig(self._chat_frame_id, width=event.width)

    def _on_chat_mousewheel(self, event):
        self._chat_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_scroll(self, widget):
        """Recursively bind mousewheel so scrolling works over bubbles."""
        widget.bind("<MouseWheel>", self._on_chat_mousewheel)
        for child in widget.winfo_children():
            self._bind_scroll(child)

    def _scroll_to_bottom(self):
        self._chat_canvas.update_idletasks()
        self._chat_canvas.yview_moveto(1.0)

    def _append_chat(self, tag: str, prefix: str, text: str,
                     msg_ref: dict | None = None):
        def _do():
            is_user = (tag == "user")
            bubble_bg = BUBBLE_USER if is_user else BUBBLE_GLADOS
            text_fg = "#ffffff"
            name_fg = USER_CLR if is_user else GLADOS_CLR

            # Outer row for left/right alignment
            row = tk.Frame(self._chat_frame, bg=BG2)
            row.pack(fill=tk.X, padx=8, pady=3)

            # Bubble
            bubble = tk.Frame(row, bg=bubble_bg, padx=12, pady=8)
            side = tk.RIGHT if is_user else tk.LEFT
            pad_l = 80 if is_user else 0
            pad_r = 0 if is_user else 80
            bubble.pack(anchor=tk.E if is_user else tk.W,
                        side=side, padx=(pad_l, pad_r))

            # Name
            tk.Label(bubble, text=prefix, font=("Consolas", 9, "bold"),
                     fg=name_fg, bg=bubble_bg, anchor=tk.W).pack(anchor=tk.W)

            # Body text with wrapping
            wrap = max(200, self._chat_canvas.winfo_width() - 180)
            tk.Label(bubble, text=text, font=("Consolas", 11),
                     fg=text_fg, bg=bubble_bg, anchor=tk.W,
                     justify=tk.LEFT, wraplength=wrap).pack(anchor=tk.W)

            # Rewind button for GLaDOS bubbles
            if msg_ref is not None:
                self._rewind_map[id(bubble)] = (msg_ref, row)
                rw_btn = tk.Button(
                    bubble, text="\u23EA", command=lambda: self._do_rewind(bubble),
                    font=("Consolas", 9), bg=bubble_bg, fg=TEXT_DIM,
                    activebackground=ACCENT, activeforeground=BG,
                    relief=tk.FLAT, padx=4, pady=0, cursor="hand2", borderwidth=0,
                )
                hide_id = [None]

                def _show(e, btn=rw_btn):
                    if hide_id[0]:
                        bubble.after_cancel(hide_id[0])
                        hide_id[0] = None
                    btn.place(relx=1.0, rely=0, anchor=tk.NE, x=-2, y=2)

                def _sched_hide(e, btn=rw_btn):
                    if hide_id[0]:
                        bubble.after_cancel(hide_id[0])
                    hide_id[0] = bubble.after(300, lambda: btn.place_forget())

                bubble.bind("<Enter>", _show)
                bubble.bind("<Leave>", _sched_hide)
                rw_btn.bind("<Enter>", _show)
                rw_btn.bind("<Leave>", _sched_hide)
                for child in bubble.winfo_children():
                    child.bind("<Enter>", _show)
                    child.bind("<Leave>", _sched_hide)

            self._chat_bubbles.append((row, tag, msg_ref))
            self._bind_scroll(row)
            self._scroll_to_bottom()
        self.after(0, _do)

    def _append_system(self, text: str):
        def _do():
            row = tk.Frame(self._chat_frame, bg=BG2)
            row.pack(fill=tk.X, padx=8, pady=2)
            tk.Label(row, text=text, font=("Consolas", 10, "italic"),
                     fg=TEXT_DIM, bg=BG2).pack(anchor=tk.CENTER)
            self._chat_bubbles.append((row, "system", None))
            self._bind_scroll(row)
            self._scroll_to_bottom()
        self.after(0, _do)

    # ---------------------------------------------------------------- callbacks (from engine threads)
    def _cb_status(self, status: str):
        self._current_status = status
        def _do():
            self.status_label.configure(text=status)
            # Enable skip button only while speaking
            if status == "Speaking":
                self.btn_skip.configure(state=tk.NORMAL, fg=TEXT)
            else:
                self.btn_skip.configure(state=tk.DISABLED, fg=TEXT_DIM)
            colour = {
                "Listening": SUCCESS,
                "Speech detected": METER_SPEECH,
                "Calibrating": WARNING,
                "Processing": WARNING,
                "Transcribing": WARNING,
                "Thinking": WARNING,
                "Speaking": ACCENT,
                "Ready": SUCCESS,
            }
            # Match partial keys (e.g. "Transcribing (2.1s)")
            dot_clr = TEXT_DIM
            for key, clr in colour.items():
                if status.startswith(key):
                    dot_clr = clr
                    break
            self.status_dot.configure(fg=dot_clr)
        self.after(0, _do)

    def _cb_message(self, role: str, text: str):
        if role == "user":
            self._append_chat("user", "You", text)
        else:
            # Pass the actual message dict reference for rewind tracking.
            # The assistant message is always appended to engine.messages
            # before this callback is invoked.
            self._append_chat("glados", "GLaDOS", text,
                              msg_ref=self.engine.messages[-1])

    def _cb_volume(self, rms, ambient, threshold, is_speech):
        self._meter_rms = rms
        self._meter_ambient = ambient
        self._meter_threshold = threshold
        self._meter_speech = is_speech

    def _cb_error(self, error: str):
        def _do():
            row = tk.Frame(self._chat_frame, bg=BG2)
            row.pack(fill=tk.X, padx=8, pady=2)
            tk.Label(row, text=f"[Error] {error}", font=("Consolas", 10),
                     fg=ERROR, bg=BG2).pack(anchor=tk.W, padx=10)
            self._chat_bubbles.append((row, "error", None))
            self._bind_scroll(row)
            self._scroll_to_bottom()
        self.after(0, _do)

    # ---------------------------------------------------------------- meter
    def _refresh_meter(self):
        """Redraw the volume meter ~20 fps."""
        c = self.meter_canvas
        c.delete("all")
        w = c.winfo_width() or 400
        h = c.winfo_height() or 22

        # Scale: map 0..0.15 RMS to full bar width (clamp)
        scale = min(self._meter_rms / 0.15, 1.0)
        bar_w = int(w * scale)

        colour = METER_SPEECH if self._meter_speech else METER_IDLE
        if bar_w > 1:
            c.create_rectangle(0, 0, bar_w, h, fill=colour, outline="")

        # Threshold marker
        thresh_x = int(w * min(self._meter_threshold / 0.15, 1.0))
        if thresh_x > 0:
            c.create_line(thresh_x, 0, thresh_x, h, fill=WARNING, width=2, dash=(4, 2))

        # Ambient marker
        amb_x = int(w * min(self._meter_ambient / 0.15, 1.0))
        if amb_x > 0:
            c.create_line(amb_x, 0, amb_x, h, fill=TEXT_DIM, width=1, dash=(2, 2))

        # Label
        self.meter_label.configure(
            text=f"RMS {self._meter_rms:.4f} | Amb {self._meter_ambient:.4f}"
        )

        self.after(50, self._refresh_meter)

    # ---------------------------------------------------------------- audio poll
    def _poll_audio(self):
        """Check for auto-captured speech from the engine's VAD."""
        try:
            audio = self.engine.audio_queue.get_nowait()
            # Pause listening while processing
            self.engine.stop_listening()

            def _work():
                self.engine.process_speech(audio)
                if self.mic_on.get():
                    self.engine.start_listening()

            self.engine.submit(_work)
        except Exception:
            pass
        if self._poll_active:
            self.after(50, self._poll_audio)

    # ---------------------------------------------------------------- user actions
    def _on_send(self, event=None):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)

        was_listening = self.engine.listening
        self.engine.stop_listening()

        def _work():
            self.engine.process_text(text)
            if was_listening and self.mic_on.get():
                self.engine.start_listening()

        self.engine.submit(_work)

    def _toggle_mic(self):
        self.settings["vad"]["enabled"] = self.mic_on.get()
        if self.mic_on.get():
            self.engine.start_listening()
        else:
            self.engine.stop_listening()
            self._cb_status("Mic off")

    def _skip_speech(self):
        """Stop TTS playback and return to listening."""
        import logging, traceback
        log = logging.getLogger("glados")
        log.info("Skip pressed, status=%r", getattr(self, '_current_status', ''))
        if getattr(self, '_current_status', '') != "Speaking":
            return
        try:
            self.engine.stop_speaking()
        except Exception:
            log.error("skip_speech error:\n%s", traceback.format_exc())

    # ---------------------------------------------------------------- rewind
    def _do_rewind(self, bubble):
        """Rewind conversation history to the selected assistant message."""
        key = id(bubble)
        if key not in self._rewind_map:
            return
        msg_ref, target_row = self._rewind_map[key]
        try:
            msg_idx = self.engine.messages.index(msg_ref)
        except ValueError:
            return
        self.engine.messages = self.engine.messages[:msg_idx + 1]
        # Find the target row's position in the bubble list and destroy everything after it
        found = False
        to_remove = []
        for row, role, ref in self._chat_bubbles:
            if found:
                to_remove.append((row, role, ref))
            elif row is target_row:
                found = True
        for row, role, ref in to_remove:
            row.destroy()
        self._chat_bubbles = [(r, rl, rf) for r, rl, rf in self._chat_bubbles
                              if r.winfo_exists()]
        # Clean up stale rewind entries
        self._rewind_map = {k: v for k, v in self._rewind_map.items()
                            if v[0] in self.engine.messages}
        self._append_system(f"Conversation rewound — {len(self.engine.messages) - 1} messages kept.")

    def _clear_chat(self):
        for row, _role, _ref in self._chat_bubbles:
            row.destroy()
        self._chat_bubbles.clear()
        self._rewind_map.clear()
        self.engine.clear_history()
        self._append_system("Chat cleared.")

    def _on_close(self):
        self.engine.shutdown()
        self.destroy()

    # ---------------------------------------------------------------- settings dialog
    def _open_settings(self):
        SettingsDialog(self, self.settings)


# ===================================================================
# Settings dialog
# ===================================================================
class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: GladosApp, settings: dict):
        super().__init__(parent)
        self.parent_app = parent
        self.settings = settings
        import copy
        self._original = copy.deepcopy(settings)
        self.title("Settings")
        self.geometry("620x560")
        self.minsize(520, 450)
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        # Notebook (tabs)
        style = ttk.Style(self)
        style.configure("Dark.TNotebook", background=BG, borderwidth=0)
        style.configure("Dark.TNotebook.Tab",
                        background=BG3, foreground=TEXT,
                        padding=[12, 4], font=("Consolas", 10))
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", BG2)],
                  foreground=[("selected", ACCENT)])
        style.configure("Dark.TFrame", background=BG2)

        self.notebook = ttk.Notebook(self, style="Dark.TNotebook")
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))

        # Build tabs
        self._vars: dict = {}
        self._build_general_tab()
        self._build_llm_tab()
        self._build_vad_tab()
        self._build_audio_tab()
        self._build_pronunciation_tab()

        # Bottom buttons
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        for text, cmd in [("Reset Defaults", self._reset_defaults),
                          ("Load", self._load_file),
                          ("Undo Changes", self._undo_changes),
                          ("Apply & Close", self._apply)]:
            tk.Button(btn_frame, text=text, command=cmd,
                      **self._btn()).pack(side=tk.LEFT, padx=(0, 6))

    def _btn(self):
        return dict(
            font=("Consolas", 10, "bold"), bg=BG3, fg=TEXT,
            activebackground=ACCENT, activeforeground=BG,
            relief=tk.FLAT, padx=10, pady=4, cursor="hand2", borderwidth=0,
        )

    def _make_tab(self, title: str) -> tk.Frame:
        frame = tk.Frame(self.notebook, bg=BG2)
        self.notebook.add(frame, text=f"  {title}  ")
        return frame

    def _label(self, parent, text, row, col=0):
        tk.Label(parent, text=text, font=("Consolas", 10),
                 fg=TEXT, bg=BG2, anchor=tk.W).grid(
            row=row, column=col, sticky=tk.W, padx=10, pady=(8, 2))

    def _entry(self, parent, key, row, width=50):
        var = tk.StringVar(value=str(self._get_nested(key)))
        self._vars[key] = var
        e = tk.Entry(parent, textvariable=var, font=("Consolas", 10),
                     bg=BG3, fg=TEXT, insertbackground=TEXT,
                     relief=tk.FLAT, borderwidth=4, width=width)
        e.grid(row=row, column=1, sticky=tk.EW, padx=10, pady=(8, 2))
        return e

    def _slider(self, parent, key, row, from_, to, resolution=0.1):
        var = tk.DoubleVar(value=float(self._get_nested(key)))
        self._vars[key] = var
        frame = tk.Frame(parent, bg=BG2)
        frame.grid(row=row, column=1, sticky=tk.EW, padx=10, pady=(8, 2))
        s = tk.Scale(frame, variable=var, from_=from_, to=to, resolution=resolution,
                     orient=tk.HORIZONTAL, bg=BG2, fg=TEXT, troughcolor=BG3,
                     highlightbackground=BG2, activebackground=ACCENT,
                     font=("Consolas", 9), length=280, borderwidth=0)
        s.pack(fill=tk.X)
        return s

    def _dropdown(self, parent, key, row, options):
        var = tk.StringVar(value=str(self._get_nested(key)))
        self._vars[key] = var
        om = ttk.Combobox(parent, textvariable=var, values=options,
                          state="readonly", font=("Consolas", 10), width=20)
        om.grid(row=row, column=1, sticky=tk.W, padx=10, pady=(8, 2))
        return om

    def _text_area(self, parent, key, row, height=5):
        self._label(parent, "", row)  # spacer
        frame = tk.Frame(parent, bg=BG2)
        frame.grid(row=row, column=0, columnspan=2, sticky=tk.NSEW, padx=10, pady=(2, 2))
        t = tk.Text(frame, font=("Consolas", 10), bg=BG3, fg=TEXT,
                    insertbackground=TEXT, relief=tk.FLAT, borderwidth=4,
                    height=height, wrap=tk.WORD)
        t.insert("1.0", str(self._get_nested(key)))
        t.pack(fill=tk.BOTH, expand=True)
        self._vars[key] = t  # store widget, not var
        return t

    def _get_nested(self, key: str):
        parts = key.split(".")
        v = self.settings
        for p in parts:
            v = v[p]
        return v

    def _set_nested(self, key: str, value):
        parts = key.split(".")
        d = self.settings
        for p in parts[:-1]:
            d = d[p]
        d[parts[-1]] = value

    # ---- tabs ----
    def _build_general_tab(self):
        tab = self._make_tab("General")
        tab.columnconfigure(1, weight=1)

        self._label(tab, "System Prompt:", 0)
        self._text_area(tab, "general.system_prompt", 1, height=6)

        self._label(tab, "Greeting Message:", 2)
        self._entry(tab, "general.greeting", 3, width=60)

    def _build_llm_tab(self):
        tab = self._make_tab("Model")
        tab.columnconfigure(1, weight=1)

        self._label(tab, "Language Model:", 0)
        current_model = self.settings["llm"]["model"]
        model_options = [m["id"] for m in LLM_MODELS]
        if current_model not in model_options:
            model_options.append(current_model)
        var = tk.StringVar(value=current_model)
        self._vars["llm.model"] = var

        # Row 0: dropdown + download button
        model_row = tk.Frame(tab, bg=BG2)
        model_row.grid(row=0, column=1, sticky=tk.EW, padx=10, pady=(8, 2))

        self._model_combo = ttk.Combobox(model_row, textvariable=var, values=model_options,
                                         state="readonly", font=("Consolas", 10), width=30)
        self._model_combo.pack(side=tk.LEFT)

        self._model_dl_btn = tk.Button(
            model_row, text="Download", command=self._download_selected_model,
            font=("Consolas", 9, "bold"), bg=ACCENT, fg=BG,
            activebackground=ACCENT_HOVER, activeforeground=BG,
            relief=tk.FLAT, padx=8, pady=2, cursor="hand2", borderwidth=0,
        )
        self._model_dl_btn.pack(side=tk.LEFT, padx=(8, 0))

        # Row 1: progress bar (hidden until download starts)
        self._model_progress = ttk.Progressbar(
            tab, mode="determinate", maximum=100, length=400,
        )
        self._model_progress.grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=20, pady=(2, 0))
        self._model_progress.grid_remove()  # hidden by default

        # Row 2: status label
        self._model_status = tk.Label(tab, text="", font=("Consolas", 8),
                                      fg=TEXT_DIM, bg=BG2, anchor=tk.W)
        self._model_status.grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=20, pady=(0, 4))

        self._label(tab, "Temperature:", 3)
        self._slider(tab, "llm.temperature", 3, 0.0, 2.0, 0.05)

        self._label(tab, "Max Tokens:", 4)
        self._slider(tab, "llm.num_predict", 4, 50, 2000, 50)

    def _download_selected_model(self):
        """Download the model currently selected in the dropdown."""
        model_id = self._vars["llm.model"].get()

        # Check if already cached
        if _is_model_cached(model_id):
            self._model_status.configure(text=f"{model_id} is already downloaded.", fg=SUCCESS)
            return

        self._model_dl_btn.configure(state=tk.DISABLED, text="Downloading...")
        self._model_progress.grid()  # show progress bar
        self._model_status.configure(text="Starting download...", fg=TEXT_DIM)

        def _thread():
            try:
                from huggingface_hub import HfApi, snapshot_download
                try:
                    from huggingface_hub.constants import HF_HUB_CACHE
                except ImportError:
                    HF_HUB_CACHE = str(Path.home() / ".cache" / "huggingface" / "hub")

                self.after(0, lambda: self._model_status.configure(text="Fetching model info..."))
                api = HfApi()
                info = api.model_info(model_id)
                total_size = sum(s.size for s in info.siblings if s.size) or 1
                total_mb = total_size / (1024 * 1024)

                cache_dir = Path(HF_HUB_CACHE) / f"models--{model_id.replace('/', '--')}"

                def get_cache_size():
                    try:
                        return sum(f.stat().st_size for f in cache_dir.rglob("*") if f.is_file())
                    except Exception:
                        return 0

                initial_size = get_cache_size()
                done = threading.Event()
                dl_error = [None]

                def _do_download():
                    try:
                        snapshot_download(model_id)
                    except Exception as e:
                        dl_error[0] = e
                    done.set()

                threading.Thread(target=_do_download, daemon=True).start()

                while not done.is_set():
                    current = max(get_cache_size() - initial_size, 0)
                    pct = min(current / total_size * 100, 99)
                    mb = current / (1024 * 1024)
                    self.after(0, lambda p=pct: self._model_progress.configure(value=p))
                    self.after(0, lambda: self._model_status.configure(
                        text=f"Downloading... {mb:,.0f} / {total_mb:,.0f} MB"))
                    done.wait(0.5)

                if dl_error[0]:
                    raise dl_error[0]

                self.after(0, lambda: self._model_progress.configure(value=100))
                self.after(0, lambda: self._model_status.configure(
                    text=f"{model_id} downloaded. Click Apply to switch.", fg=SUCCESS))
                self.after(0, lambda: self._model_dl_btn.configure(state=tk.NORMAL, text="Download"))

            except Exception as e:
                self.after(0, lambda: self._model_status.configure(text=f"Error: {e}", fg=ERROR))
                self.after(0, lambda: self._model_dl_btn.configure(state=tk.NORMAL, text="Retry"))

        threading.Thread(target=_thread, daemon=True).start()

    def _build_vad_tab(self):
        tab = self._make_tab("Voice Detection")
        tab.columnconfigure(1, weight=1)

        self._label(tab, "Activation Sensitivity:", 0)
        self._slider(tab, "vad.activation_mult", 0, 1.5, 10.0, 0.25)

        self._label(tab, "Noise Gate (chunks):", 1)
        self._slider(tab, "vad.noise_gate", 1, 1, 15, 1)

        self._label(tab, "Ambient Absorption:", 2)
        self._slider(tab, "vad.ambient_absorption", 2, 1.0, 3.0, 0.1)

        self._label(tab, "Silence Timeout (s):", 3)
        self._slider(tab, "vad.silence_timeout", 3, 0.3, 5.0, 0.1)

        self._label(tab, "Min Speech Duration (s):", 4)
        self._slider(tab, "vad.min_speech_sec", 4, 0.1, 3.0, 0.1)

        self._label(tab, "RMS Floor:", 5)
        self._slider(tab, "vad.rms_floor", 5, 0.001, 0.05, 0.001)

        self._label(tab, "Pre-Speech Buffer (s):", 6)
        self._slider(tab, "vad.pre_speech_sec", 6, 0.1, 1.0, 0.05)

        self._label(tab, "Calibration Duration (s):", 7)
        self._slider(tab, "vad.calibration_sec", 7, 0.5, 5.0, 0.25)

        self._label(tab, "Ambient Window (s):", 8)
        self._slider(tab, "vad.ambient_window_sec", 8, 0.5, 10.0, 0.5)

    def _build_audio_tab(self):
        tab = self._make_tab("Audio")
        tab.columnconfigure(1, weight=1)

        self._label(tab, "Volume:", 0)
        self._slider(tab, "audio.volume", 0, 0.0, 2.0, 0.05)

        self._label(tab, "Sample Rate:", 1)
        self._dropdown(tab, "audio.sample_rate", 1,
                       ["16000", "22050", "44100"])

        self._label(tab, "Input Device:", 2)
        devices = GladosEngine.get_input_devices()
        self._device_map = {d[1]: d[0] for d in devices}
        names = [d[1] for d in devices]
        current = self.settings["audio"]["input_device"]
        current_name = "System Default"
        for idx, name in devices:
            if idx == current:
                current_name = name
                break
        names.insert(0, "System Default")
        self._device_map["System Default"] = None
        var = tk.StringVar(value=current_name)
        self._vars["audio.input_device"] = var
        om = ttk.Combobox(tab, textvariable=var, values=names,
                          state="readonly", font=("Consolas", 10), width=40)
        om.grid(row=2, column=1, sticky=tk.W, padx=10, pady=(8, 2))

    def _build_pronunciation_tab(self):
        tab = self._make_tab("Pronunciation")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        # Header
        tk.Label(tab, text="Fix TTS pronunciations (applied before speech synthesis)",
                 font=("Consolas", 9), fg=TEXT_DIM, bg=BG2, anchor=tk.W
                 ).grid(row=0, column=0, sticky=tk.W, padx=10, pady=(8, 2))

        # Scrollable list area
        list_frame = tk.Frame(tab, bg=BG2)
        list_frame.grid(row=1, column=0, sticky=tk.NSEW, padx=10, pady=(4, 4))
        list_frame.columnconfigure(0, weight=1)

        canvas = tk.Canvas(list_frame, bg=BG2, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=canvas.yview)
        self._pron_inner = tk.Frame(canvas, bg=BG2)
        self._pron_inner.bind("<Configure>",
                              lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._pron_inner, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._pron_rows: list[tuple[tk.Entry, tk.Entry, tk.Button]] = []
        replacements = self.settings.get("tts_replacements", {})
        for find, replace in replacements.items():
            self._add_pron_row(find, replace)

        # Add button
        btn_frame = tk.Frame(tab, bg=BG2)
        btn_frame.grid(row=2, column=0, sticky=tk.W, padx=10, pady=(0, 8))
        tk.Button(btn_frame, text="+ Add Rule", command=lambda: self._add_pron_row("", ""),
                  font=("Consolas", 9, "bold"), bg=BG3, fg=TEXT,
                  activebackground=ACCENT, activeforeground=BG,
                  relief=tk.FLAT, padx=8, pady=2, cursor="hand2", borderwidth=0,
                  ).pack(side=tk.LEFT)

    def _add_pron_row(self, find: str = "", replace: str = ""):
        row_frame = tk.Frame(self._pron_inner, bg=BG2)
        row_frame.pack(fill=tk.X, pady=2)

        tk.Label(row_frame, text="Say", font=("Consolas", 9),
                 fg=TEXT_DIM, bg=BG2).pack(side=tk.LEFT, padx=(0, 4))
        find_entry = tk.Entry(row_frame, font=("Consolas", 10),
                              bg=BG3, fg=TEXT, insertbackground=TEXT,
                              relief=tk.FLAT, borderwidth=4, width=20)
        find_entry.insert(0, find)
        find_entry.pack(side=tk.LEFT, padx=(0, 6))

        tk.Label(row_frame, text="as", font=("Consolas", 9),
                 fg=TEXT_DIM, bg=BG2).pack(side=tk.LEFT, padx=(0, 4))
        replace_entry = tk.Entry(row_frame, font=("Consolas", 10),
                                 bg=BG3, fg=TEXT, insertbackground=TEXT,
                                 relief=tk.FLAT, borderwidth=4, width=20)
        replace_entry.insert(0, replace)
        replace_entry.pack(side=tk.LEFT, padx=(0, 6))

        del_btn = tk.Button(row_frame, text="\u2715", command=lambda: self._del_pron_row(row_frame),
                            font=("Consolas", 9, "bold"), bg=BG3, fg=ERROR,
                            activebackground=ERROR, activeforeground=BG,
                            relief=tk.FLAT, padx=4, pady=0, cursor="hand2", borderwidth=0)
        del_btn.pack(side=tk.LEFT)

        self._pron_rows.append((find_entry, replace_entry, del_btn, row_frame))

    def _del_pron_row(self, row_frame):
        self._pron_rows = [(f, r, b, rf) for f, r, b, rf in self._pron_rows if rf is not row_frame]
        row_frame.destroy()

    # ---- actions ----
    def _collect(self):
        """Read all widget values back into self.settings."""
        for key, var in self._vars.items():
            try:
                if isinstance(var, tk.Text):
                    val = var.get("1.0", tk.END).strip()
                elif isinstance(var, tk.DoubleVar):
                    val = var.get()
                elif isinstance(var, tk.StringVar):
                    val = var.get()
                else:
                    continue
            except tk.TclError:
                continue

            # Type coerce for known numeric fields
            if key == "audio.input_device":
                val = self._device_map.get(val)
            elif key in ("audio.sample_rate", "llm.num_predict",
                         "vad.noise_gate"):
                val = int(float(val))
            elif key in ("llm.temperature", "audio.volume",
                         "vad.activation_mult", "vad.ambient_absorption",
                         "vad.silence_timeout",
                         "vad.min_speech_sec", "vad.rms_floor",
                         "vad.pre_speech_sec", "vad.calibration_sec",
                         "vad.ambient_window_sec"):
                val = float(val)

            self._set_nested(key, val)

        # Collect pronunciation replacements
        replacements = {}
        for find_e, replace_e, _btn, _frame in self._pron_rows:
            find = find_e.get().strip()
            replace = replace_e.get().strip()
            if find:
                replacements[find] = replace
        self.settings["tts_replacements"] = replacements

    def _apply(self):
        old_model = self.settings["llm"]["model"]
        self._collect()
        save_settings(self.settings)
        # Push updated settings into the engine
        self.parent_app.engine.settings = self.settings
        new_model = self.settings["llm"]["model"]
        self.destroy()

        # Restart the audio stream so VAD/audio changes take effect
        if new_model == old_model:
            app = self.parent_app
            if app.engine.listening:
                app.engine.stop_listening()
                app.engine.start_listening()

        # If the model changed and the new one is cached, hot-swap it
        if new_model != old_model and _is_model_cached(new_model):
            app = self.parent_app
            # Signal boot thread to abort, stop audio poll loop
            app._model_switching = True
            app._poll_active = False
            app.engine.stop_speaking()
            app.engine.stop_listening()
            app._cb_status(f"Switching to {new_model}...")

            def _reload():
                import gc, torch
                # Wait for any in-progress initialize() to finish
                with app.engine._init_lock:
                    app.engine._unload_model()
                    gc.collect()
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                app._model_switching = False
                app.engine.initialize()
                app.engine.clear_history()
                greeting = app.settings["general"]["greeting"]
                app.engine.messages.append({"role": "assistant", "content": greeting})
                app._cb_message("assistant", greeting)
                app._cb_status("Speaking")
                try:
                    app.engine.speak(greeting)
                except Exception:
                    pass
                app.engine.calibrate()
                app._cb_status("Listening")
                # Restart the poll loop
                app._poll_active = True
                app.after(50, app._poll_audio)

            threading.Thread(target=_reload, daemon=True).start()

    def _reset_defaults(self):
        defaults = get_defaults()
        # Overwrite all current settings
        for section in defaults:
            self.settings[section] = defaults[section]
        # Refresh widgets
        self.destroy()
        SettingsDialog(self.parent_app, self.settings)

    def _undo_changes(self):
        import copy
        for section in self._original:
            self.settings[section] = copy.deepcopy(self._original[section])
        self.destroy()
        SettingsDialog(self.parent_app, self.settings)

    def _load_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json")],
            title="Load Settings",
        )
        if path:
            try:
                with open(path, "r") as f:
                    loaded = json.load(f)
                for section in self.settings:
                    if section in loaded:
                        self.settings[section].update(loaded[section])
                self.destroy()
                SettingsDialog(self.parent_app, self.settings)
            except Exception as e:
                messagebox.showerror("Load Error", str(e))


# ===================================================================
# Entry point
# ===================================================================
if __name__ == "__main__":
    need_pkgs = not _DEPS_READY
    need_tts = not (TTS_DIR / "glados" / "models" / "glados.onnx").exists()

    if need_pkgs or need_tts:
        # Show setup dialog in a temporary root window
        _root = tk.Tk()
        _root.withdraw()
        _dlg = SetupDialog(_root, need_pkgs=need_pkgs, need_tts=need_tts)
        _root.wait_window(_dlg)
        _root.destroy()
        if _dlg.success:
            # Restart so fresh imports pick up the newly installed packages
            subprocess.Popen([sys.executable] + sys.argv)
            sys.exit(0)
        else:
            sys.exit(1)

    app = GladosApp()
    app.mainloop()
