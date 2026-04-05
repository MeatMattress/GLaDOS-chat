#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  GLaDOS Voice Chat — First Time Setup"
echo "============================================================"
echo

# ---- Check Python ----
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERROR] Python not found. Install Python 3.10+ and add to PATH."
    exit 1
fi
echo "  Python: $($PYTHON --version)"

# ---- Check git ----
if ! command -v git &>/dev/null; then
    echo "[ERROR] git not found. Install git and add to PATH."
    exit 1
fi

# ---- Create venv ----
echo
echo "[1/3] Setting up virtual environment..."
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
fi
source venv/bin/activate
echo "       Done."

# ---- Install dependencies ----
echo
echo "[2/3] Installing Python dependencies (this may take a while)..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "       Done."

# ---- Download models ----
echo
echo "[3/3] Downloading models..."
python setup_models.py "$@"

echo
echo "  Setup complete! Run ./run.sh to start GLaDOS Chat."
echo
