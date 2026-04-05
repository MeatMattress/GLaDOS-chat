"""
Cross-platform model downloader for GLaDOS Voice Chat.
Downloads GLaDOS TTS models and optionally pre-downloads the Gemma 4 LLM.
Works on Windows, Linux, and macOS.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
TTS_DIR = BASE_DIR / "GLaDOS-TTS"
MODELS_DIR = TTS_DIR / "glados" / "models"
SETTINGS_FILE = BASE_DIR / "settings.json"

TTS_REPO = "https://github.com/nimaid/GLaDOS-TTS.git"

ONNX_MODELS = {
    "glados.onnx": "https://github.com/dnhkng/GlaDOS/releases/download/0.1/glados.onnx",
    "phomenizer_en.onnx": "https://github.com/dnhkng/GlaDOS/releases/download/0.1/phomenizer_en.onnx",
}

DEFAULT_LLM = "google/gemma-4-E2B-it"


# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------
def _progress_bar(current: int, total: int, width: int = 40, label: str = ""):
    if total <= 0:
        return
    frac = current / total
    filled = int(width * frac)
    bar = "\u2588" * filled + "\u2591" * (width - filled)
    mb_cur = current / (1024 * 1024)
    mb_tot = total / (1024 * 1024)
    sys.stdout.write(f"\r  {label} [{bar}] {mb_cur:6.1f} / {mb_tot:.1f} MB ({frac:.0%})")
    sys.stdout.flush()


def download_file(url: str, dest: Path, label: str = ""):
    """Download a file with a progress bar."""
    label = label or dest.name
    tmp = dest.with_suffix(dest.suffix + ".tmp")

    req = urllib.request.Request(url, headers={"User-Agent": "GLaDOS-Chat-Setup/1.0"})

    try:
        with urllib.request.urlopen(req) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 1024 * 256  # 256 KB

            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    _progress_bar(downloaded, total, label=label)
        print()  # newline after progress bar
        shutil.move(str(tmp), str(dest))
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------
def clone_tts_repo():
    """Clone the GLaDOS-TTS repository if it doesn't exist."""
    if (TTS_DIR / "glados" / "__init__.py").exists():
        print("  GLaDOS-TTS repo .......... already present")
        return

    print("  Cloning GLaDOS-TTS repo...")
    subprocess.check_call(
        ["git", "clone", "--depth", "1", TTS_REPO, str(TTS_DIR)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("  GLaDOS-TTS repo .......... done")


def download_tts_models():
    """Download the ONNX TTS model files."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for filename, url in ONNX_MODELS.items():
        dest = MODELS_DIR / filename
        if dest.exists() and dest.stat().st_size > 1_000_000:
            print(f"  {filename} ............. already downloaded")
            continue
        download_file(url, dest, label=filename)


def download_llm():
    """Pre-download the Gemma 4 model via HuggingFace Hub."""
    # Read model ID from settings if available
    model_id = DEFAULT_LLM
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE) as f:
                model_id = json.load(f).get("llm", {}).get("model", DEFAULT_LLM)
        except Exception:
            pass

    print(f"\n  Pre-downloading {model_id}...")
    print("  (HuggingFace shows its own progress below)\n")

    try:
        from huggingface_hub import snapshot_download
        snapshot_download(model_id)
        print(f"\n  {model_id} .... done")
    except ImportError:
        print("  huggingface_hub not installed — model will download on first launch.")
    except Exception as e:
        print(f"\n  [Warning] LLM pre-download failed: {e}")
        print("  The model will download automatically on first launch.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print()
    print("=" * 60)
    print("  GLaDOS Voice Chat — Model Setup")
    print("=" * 60)
    print()

    # Step 1: GLaDOS-TTS repo
    print("[1/3] GLaDOS TTS repository")
    clone_tts_repo()
    print()

    # Step 2: ONNX models
    print("[2/3] GLaDOS TTS models (~120 MB)")
    download_tts_models()
    print()

    # Step 3: Gemma 4 LLM
    print("[3/3] Gemma 4 E2B language model (~4-5 GB)")

    if "--skip-llm" in sys.argv:
        print("  Skipped (--skip-llm). Will download on first launch.")
    else:
        download_llm()

    print()
    print("=" * 60)
    print("  Setup complete! Run the app:")
    if sys.platform == "win32":
        print("    run.bat           (GUI)")
        print("    run.bat --cli     (terminal mode)")
    else:
        print("    ./run.sh          (GUI)")
        print("    ./run.sh --cli    (terminal mode)")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
