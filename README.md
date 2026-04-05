# GLaDOS Voice Chat

A voice-interactive GLaDOS chatbot powered by Google's Gemma 4 E2B multimodal model. Speak to GLaDOS through your microphone and hear her respond in her iconic voice — complete with passive-aggressive commentary and backhanded compliments.

## Features

- **Native speech recognition** — Gemma 4 E2B processes audio directly, no separate STT model needed
- **GLaDOS text-to-speech** — ONNX/VITS synthesis for authentic GLaDOS voice output
- **Adaptive voice detection** — RMS-based VAD with ambient noise baseline that adjusts to your environment
- **GUI and CLI modes** — Full tkinter interface with Portal-themed dark UI, or lightweight terminal mode
- **Configurable settings** — System prompt, model parameters, VAD tuning, audio devices, all saved to JSON
- **Real-time volume meter** — Visual RMS bar with ambient baseline and activation threshold markers

## Requirements

- **Python 3.10+**
- **Git**
- **NVIDIA GPU** with CUDA support (for Gemma 4 inference)
- ~5 GB disk space for models

## Quick Start

### Windows

```
setup.bat
run.bat
```

### Linux / macOS

```bash
chmod +x setup.sh run.sh
./setup.sh
./run.sh
```

### CLI Mode

```bash
# Windows
run.bat --cli

# Linux / macOS
./run.sh --cli
```

## Setup Details

The setup script handles everything automatically:

1. Creates a Python virtual environment
2. Installs all pip dependencies (PyTorch, Transformers, etc.)
3. Clones the [GLaDOS-TTS](https://github.com/nimaid/GLaDOS-TTS) repository
4. Downloads GLaDOS ONNX voice models (~120 MB)
5. Pre-downloads Gemma 4 E2B from HuggingFace (~4-5 GB) with progress

To skip the large LLM download during setup (it will download on first launch instead):

```bash
# Windows
setup.bat --skip-llm

# Linux / macOS
./setup.sh --skip-llm
```

## Configuration

Settings are stored in `settings.json` and can be edited through the GUI settings panel or by hand.

| Section | Key | Description |
|---------|-----|-------------|
| `general` | `system_prompt` | GLaDOS personality prompt |
| `general` | `greeting` | Opening message on launch |
| `llm` | `model` | HuggingFace model ID |
| `llm` | `temperature` | Response randomness (0.0 - 2.0) |
| `llm` | `num_predict` | Max response tokens |
| `vad` | `activation_mult` | Mic sensitivity multiplier |
| `vad` | `noise_gate` | Consecutive chunks required to trigger |
| `vad` | `ambient_absorption` | How aggressively ambient baseline adapts upward |
| `vad` | `silence_timeout` | Seconds of silence before processing |
| `audio` | `volume` | TTS output volume (0.0 - 2.0) |
| `audio` | `input_device` | Microphone device index (`null` for system default) |

## Project Structure

```
GLaDOS-Chat/
├── glados_gui.py        # Tkinter GUI application
├── glados_chat.py       # CLI application
├── glados_engine.py     # Core engine (VAD, LLM, TTS)
├── setup_models.py      # Cross-platform model downloader
├── settings.json        # User configuration
├── requirements.txt     # Python dependencies
├── setup.bat / setup.sh # Platform setup scripts
├── run.bat / run.sh     # Platform launch scripts
└── GLaDOS-TTS/          # Cloned during setup (not in repo)
```

## Troubleshooting

**PyTorch not using GPU** — The default `torch` pip package is CPU-only. Install the CUDA build:
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
```

**Mic not detected** — Check `audio.input_device` in settings, or select a device in the GUI Audio tab. Use `null` for system default.

**VAD too sensitive / not sensitive enough** — Adjust `vad.activation_mult` (higher = less sensitive) and `vad.noise_gate` (higher = requires more sustained sound to trigger).

## Credits

- [Gemma 4](https://ai.google.dev/gemma) by Google — multimodal language model with native audio
- [GLaDOS-TTS](https://github.com/nimaid/GLaDOS-TTS) by nimaid — ONNX voice synthesis
- [Portal](https://store.steampowered.com/app/400/Portal/) by Valve — GLaDOS character
