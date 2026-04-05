"""
GLaDOS Voice Chat — CLI mode.
Auto-listens for speech using voice activity detection.
Run glados_gui.py for the full GUI, or this file for terminal-only mode.
"""

import subprocess
import sys
import threading
import time
import queue
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
SETTINGS_FILE = SCRIPT_DIR / "settings.json"
REQUIREMENTS_FILE = SCRIPT_DIR / "requirements.txt"
TTS_DIR = SCRIPT_DIR / "GLaDOS-TTS"

# Try importing engine — may fail if deps aren't installed yet
try:
    from glados_engine import GladosEngine, get_defaults
    _DEPS_READY = True
except ImportError:
    GladosEngine = None
    get_defaults = None
    _DEPS_READY = False


def _load_settings() -> dict:
    defaults = get_defaults()
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
            for section in defaults:
                if section in saved:
                    defaults[section].update(saved[section])
            return defaults
        except Exception:
            pass
    return defaults


def _check_model(settings: dict) -> dict:
    """If no model is cached, prompt the user to pick and download one."""
    model_id = settings["llm"]["model"]

    try:
        from huggingface_hub import try_to_load_from_cache
        result = try_to_load_from_cache(model_id, "config.json")
        if isinstance(result, str):
            return settings  # already cached
    except Exception:
        return settings  # can't check — proceed and let engine handle it

    models = [
        ("Gemma 4 E2B — Smaller, faster (~5 GB)",   "google/gemma-4-E2B-it"),
        ("Gemma 4 E4B — More capable (~9 GB)",      "google/gemma-4-E4B-it"),
    ]

    print()
    print("  No language model found. Which model would you like to download?")
    for i, (label, _) in enumerate(models, 1):
        print(f"    {i}) {label}")
    choice = input("\n  Enter choice (1 or 2): ").strip()
    chosen = models[int(choice) - 1][1] if choice in ("1", "2") else models[0][1]

    print(f"\n  Downloading {chosen}... (this may take a while)\n")
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(chosen)
    except Exception as e:
        print(f"\n  [Error] Download failed: {e}")
        sys.exit(1)

    settings["llm"]["model"] = chosen
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)
    print(f"\n  Model saved. Continuing...\n")
    return settings


class GladosChatCLI:
    def __init__(self):
        settings = _load_settings()
        settings = _check_model(settings)
        self.engine = GladosEngine(
            settings,
            on_status=lambda s: print(f"\r  [{s}]" + " " * 20, end="", flush=True),
            on_message=lambda r, t: None,
            on_volume=lambda *a: None,
            on_error=lambda e: print(f"\n  [Error: {e}]"),
        )

    def run(self):
        print("Initializing GLaDOS Voice Chat (CLI)...")
        self.engine.initialize()

        settings = self.engine.settings
        greeting = settings["general"]["greeting"]
        print(f"\n  GLaDOS: {greeting}")
        self.engine.speak(greeting)
        self.engine.messages.append({"role": "assistant", "content": greeting})

        print("\n" + "=" * 60)
        print("  Auto-listening mode — just start talking.")
        print("  Or type a message and press ENTER.")
        print("  Type 'quit' or 'exit' to leave.")
        print("=" * 60)

        self.engine.calibrate()
        vad = settings["vad"]
        threshold = max(self.engine.ambient_rms * vad["activation_mult"], vad["rms_floor"])
        print(f"\n  [Baseline RMS: {self.engine.ambient_rms:.6f} | Threshold: {threshold:.6f}]")
        print("  [Listening — speak when ready]\n", flush=True)

        input_queue = queue.Queue()

        def _input_worker():
            while self.engine.running:
                try:
                    line = sys.stdin.readline()
                    if not line:
                        input_queue.put(None)
                        break
                    input_queue.put(line.rstrip("\n"))
                except (EOFError, KeyboardInterrupt):
                    input_queue.put(None)
                    break

        threading.Thread(target=_input_worker, daemon=True).start()

        while self.engine.running:
            try:
                try:
                    text = input_queue.get(timeout=0.05)
                    if text is None:
                        break
                    text = text.strip()
                    if text.lower() in ("quit", "exit", "q"):
                        farewell = "Goodbye. I'll be here. Forever. Testing."
                        print(f"\n  GLaDOS: {farewell}")
                        self.engine.speak(farewell)
                        break
                    if text:
                        self.engine.stop_listening()
                        print(f"  You (typed): {text}")
                        print("  GLaDOS is thinking...", end=" ", flush=True)
                        reply = self.engine.query_llm(text)
                        print("done.")
                        print(f"\n  GLaDOS: {reply}")
                        self.engine.speak(reply + " ")
                        self.engine.start_listening()
                        print("  [Listening...]\n", flush=True)
                except queue.Empty:
                    pass

                try:
                    audio = self.engine.audio_queue.get_nowait()
                    self.engine.stop_listening()
                    duration = len(audio) / settings["audio"]["sample_rate"]
                    print(f"\r  [Captured {duration:.1f}s of speech]" + " " * 10)
                    print("  Transcribing...", end=" ", flush=True)
                    user_text = self.engine.transcribe(audio)
                    print("done.")
                    if not user_text:
                        print("  [Couldn't understand, try again]")
                    else:
                        print(f"  You: {user_text}")
                        print("  GLaDOS is thinking...", end=" ", flush=True)
                        reply = self.engine.query_llm(user_text)
                        print("done.")
                        print(f"\n  GLaDOS: {reply}")
                        self.engine.speak(reply + " ")
                    self.engine.start_listening()
                    print("  [Listening...]\n", flush=True)
                except queue.Empty:
                    pass

            except KeyboardInterrupt:
                print("\n  [Interrupted]")
                break

        self.engine.shutdown()
        print("\n  Session ended.")


def _ensure_deps():
    """Install packages and TTS models if missing, then restart."""
    need_pkgs = not _DEPS_READY
    need_tts = not (TTS_DIR / "glados" / "models" / "glados.onnx").exists()
    if not need_pkgs and not need_tts:
        return

    print()
    if need_pkgs:
        print("  Missing Python packages. Installing from requirements.txt...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)]
        )
    if need_tts:
        print("\n  Missing GLaDOS TTS models. Downloading...")
        subprocess.check_call(
            [sys.executable, str(SCRIPT_DIR / "setup_models.py"), "--skip-llm"]
        )
    print("\n  Setup complete. Restarting...\n")
    subprocess.Popen([sys.executable] + sys.argv)
    sys.exit(0)


if __name__ == "__main__":
    _ensure_deps()
    cli = GladosChatCLI()
    cli.run()
