#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# First time? Run setup.
if [ ! -d "venv" ]; then
    echo "First time? Running setup..."
    bash setup.sh
fi

source venv/bin/activate

# Launch GUI (use --cli for terminal mode)
if [ "$1" = "--cli" ]; then
    python glados_chat.py
else
    python glados_gui.py
fi
