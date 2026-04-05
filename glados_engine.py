"""
GLaDOS Chat Engine — core logic for VAD, LLM (Gemma 4 via Transformers), and TTS.
Designed to be driven by any frontend (CLI or GUI) via callbacks.
"""

import logging
import os
import re
import sys
import atexit
import signal
import tempfile
import threading
import time
import wave
import queue
from pathlib import Path
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Logging — writes to glados.log and stderr
# ---------------------------------------------------------------------------
LOG_FILE = Path(__file__).parent / "glados.log"
log = logging.getLogger("glados")
log.setLevel(logging.DEBUG)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
_fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(_fmt)
_sh = logging.StreamHandler(sys.stderr)
_sh.setLevel(logging.WARNING)
_sh.setFormatter(_fmt)
log.addHandler(_fh)
log.addHandler(_sh)

import numpy as np
import sounddevice as sd

# Add GLaDOS TTS to path
GLADOS_DIR = Path(__file__).parent / "GLaDOS-TTS"
sys.path.insert(0, str(GLADOS_DIR))
import glados

# ---------------------------------------------------------------------------
# Default settings — also used as the "Reset Defaults" snapshot in the GUI.
# ---------------------------------------------------------------------------
DEFAULTS = {
    "general": {
        "system_prompt": (
            "You are GLaDOS, the AI from the Portal video game series. "
            "You are passive-aggressive, darkly humorous, and condescending. "
            "You make backhanded compliments and subtle threats about testing. "
            "Keep responses concise — 1 to 3 sentences max. "
            "Never break character. Never mention being a language model."
        ),
        "greeting": "Oh. It's you. I suppose you want to talk. How... delightful.",
    },
    "llm": {
        "model": "google/gemma-4-E2B-it",
        "temperature": 0.8,
        "num_predict": 300,
    },
    "vad": {
        "enabled": True,
        "activation_mult": 3.0,
        "noise_gate": 5,
        "ambient_absorption": 1.5,
        "silence_timeout": 1.5,
        "min_speech_sec": 0.5,
        "rms_floor": 0.005,
        "pre_speech_sec": 0.3,
        "calibration_sec": 1.5,
        "ambient_window_sec": 2.0,
        "chunk_ms": 30,
    },
    "audio": {
        "sample_rate": 16000,
        "input_device": None,
        "volume": 1.0,
    },
}


def _deep_copy(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        out[k] = _deep_copy(v) if isinstance(v, dict) else v
    return out


def get_defaults() -> dict:
    return _deep_copy(DEFAULTS)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class GladosEngine:
    """
    Callback-based engine.  The owner (GUI / CLI) supplies callables:
        on_status(status_str)
        on_message(role_str, text_str)
        on_volume(rms, ambient, threshold, is_speech)
        on_error(error_str)
    All callbacks are fired from *worker* threads — the GUI must use
    thread-safe scheduling (e.g. root.after / root.event_generate).
    """

    def __init__(self, settings: dict,
                 on_status:  Callable = lambda s: None,
                 on_message: Callable = lambda r, t: None,
                 on_volume:  Callable = lambda r, a, t, s: None,
                 on_error:   Callable = lambda e: None):
        self.settings = settings
        self.on_status  = on_status
        self.on_message = on_message
        self.on_volume  = on_volume
        self.on_error   = on_error

        self.model = None
        self.processor = None
        self.tts = None
        self.messages: list = []
        self.running = True

        # VAD runtime state
        self.listening = False
        self.speech_detected = False
        self.silence_start: Optional[float] = None
        self._consecutive_above = 0
        self.audio_buffer: list = []
        self.speech_frames: list = []
        self.ambient_levels: list = []
        self.ambient_rms = 0.01
        self.stream = None
        self.audio_queue: queue.Queue = queue.Queue()

        # Worker thread for blocking operations
        self._worker_queue: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

        # Register cleanup so the model is freed on any exit
        atexit.register(self._unload_model)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT,  self._signal_handler)
        if hasattr(signal, "SIGBREAK"):
            signal.signal(signal.SIGBREAK, self._signal_handler)

    # ---- derived helpers ----
    @property
    def _sr(self):
        return self.settings["audio"]["sample_rate"]

    @property
    def _chunk_samples(self):
        return int(self._sr * self.settings["vad"]["chunk_ms"] / 1000)

    @property
    def _pre_speech_chunks(self):
        return int(self.settings["vad"]["pre_speech_sec"] * 1000 / self.settings["vad"]["chunk_ms"])

    @property
    def _ambient_window_chunks(self):
        return int(self.settings["vad"]["ambient_window_sec"] * 1000 / self.settings["vad"]["chunk_ms"])

    # ------------------------------------------------------------------ init
    def initialize(self):
        """Load heavy models (call from a thread so the GUI stays responsive)."""
        import torch
        from transformers import AutoProcessor, AutoModelForMultimodalLM

        log.info("Initializing engine...")
        model_id = self.settings["llm"]["model"]

        self.on_status(f"Loading {model_id}...")
        log.info("Loading model %s", model_id)
        try:
            self.processor = AutoProcessor.from_pretrained(model_id, local_files_only=True)
            self.model = AutoModelForMultimodalLM.from_pretrained(
                model_id,
                dtype="auto",
                device_map="auto",
                local_files_only=True,
            )
            # Clear invalid generation defaults so generate() doesn't warn
            self.model.generation_config.top_p = None
            self.model.generation_config.top_k = None
            log.info("Model loaded on %s", self.model.device)
        except Exception as e:
            log.error("Model load failed: %s", e)
            self.on_error(f"Model load failed: {e}")
            return

        self.on_status("Loading GLaDOS TTS model...")
        try:
            self.tts = glados.TTS()
        except Exception as e:
            self.on_error(f"TTS load failed: {e}")
            return

        self.messages = [
            {"role": "system", "content": self.settings["general"]["system_prompt"]}
        ]
        self.on_status("Ready")

    # --------------------------------------------------------------- cleanup
    def _signal_handler(self, sig, frame):
        self.shutdown()
        sys.exit(0)

    def _unload_model(self):
        """Free the Transformers model and release VRAM."""
        try:
            import torch
            if self.model is not None:
                log.info("Unloading model from VRAM...")
                del self.model
                self.model = None
            if self.processor is not None:
                del self.processor
                self.processor = None
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                log.info("CUDA cache cleared")
        except Exception as e:
            log.warning("Model unload failed: %s", e)

    def shutdown(self):
        self.running = False
        self.stop_listening()
        self._unload_model()

    # --------------------------------------------------------------- VAD
    def _audio_callback(self, indata, frames, time_info, status):
        if not self.listening:
            return
        vad = self.settings["vad"]
        chunk = indata[:, 0].copy()
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        threshold = max(self.ambient_rms * vad["activation_mult"], vad["rms_floor"])

        self.on_volume(rms, self.ambient_rms, threshold, self.speech_detected)

        if not self.speech_detected:
            absorb_ceiling = threshold * vad.get("ambient_absorption", 1.5)

            self.audio_buffer.append(chunk)
            if len(self.audio_buffer) > self._pre_speech_chunks:
                self.audio_buffer.pop(0)

            if rms > threshold:
                self._consecutive_above += 1
                if rms < absorb_ceiling:
                    self.ambient_levels.append(rms)
                    if len(self.ambient_levels) > self._ambient_window_chunks:
                        self.ambient_levels.pop(0)
                    self.ambient_rms = float(np.mean(self.ambient_levels))

                gate = int(vad.get("noise_gate", 5))
                if self._consecutive_above >= gate:
                    self.speech_detected = True
                    self.silence_start = None
                    self._consecutive_above = 0
                    self.speech_frames = list(self.audio_buffer)
                    self.speech_frames.append(chunk)
                    log.info("Speech onset (rms=%.5f, threshold=%.5f, gate=%d)", rms, threshold, gate)
                    self.on_status("Speech detected")
            else:
                self._consecutive_above = 0
                self.ambient_levels.append(rms)
                if len(self.ambient_levels) > self._ambient_window_chunks:
                    self.ambient_levels.pop(0)
                self.ambient_rms = float(np.mean(self.ambient_levels))
        else:
            self.speech_frames.append(chunk)
            if rms > threshold:
                self.silence_start = None
            else:
                if self.silence_start is None:
                    self.silence_start = time.monotonic()
                elif time.monotonic() - self.silence_start >= vad["silence_timeout"]:
                    audio = np.concatenate(self.speech_frames)
                    dur = len(audio) / self._sr
                    if len(audio) >= int(self._sr * vad["min_speech_sec"]):
                        log.info("Speech ended — captured %.1fs", dur)
                        self.audio_queue.put(audio)
                    else:
                        log.debug("Speech too short (%.2fs), discarding", dur)
                    self.speech_detected = False
                    self.silence_start = None
                    self.speech_frames = []
                    self.audio_buffer = []
                    self.on_status("Processing")

    def start_listening(self):
        if not self.settings["vad"]["enabled"]:
            return
        self.listening = True
        self.speech_detected = False
        self.silence_start = None
        self._consecutive_above = 0
        self.audio_buffer = []
        self.speech_frames = []

        device_index = self.settings["audio"]["input_device"]
        self.stream = sd.InputStream(
            samplerate=self._sr,
            channels=1,
            dtype="float32",
            callback=self._audio_callback,
            blocksize=self._chunk_samples,
            device=device_index,
        )
        self.stream.start()
        self.on_status("Listening")

    def stop_listening(self):
        self.listening = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def calibrate(self, duration: Optional[float] = None):
        dur = duration or self.settings["vad"]["calibration_sec"]
        self.on_status("Calibrating")
        self.ambient_levels = []
        self.start_listening()
        time.sleep(dur)
        self.on_status("Listening")

    # --------------------------------------------------------------- audio helpers
    def _save_temp_wav(self, audio: np.ndarray) -> str:
        """Save float32 mono audio to a temporary WAV file, return its path."""
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sr)
            wf.writeframes((audio * 32767).astype(np.int16).tobytes())
        return path

    # --------------------------------------------------------------- STT (Gemma 4 native audio)
    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe speech using Gemma 4's native audio encoder."""
        import torch

        if len(audio) == 0 or self.model is None:
            return ""

        duration = len(audio) / self._sr
        log.info("Transcribing %.1fs of audio via Gemma 4 audio", duration)

        # Enforce 30-second limit
        max_samples = int(self._sr * 30)
        if len(audio) > max_samples:
            log.warning("Audio exceeds 30s limit, truncating")
            audio = audio[:max_samples]

        wav_path = self._save_temp_wav(audio)
        try:
            messages = [{
                "role": "user",
                "content": [
                    {"type": "audio", "audio": wav_path},
                    {"type": "text", "text": (
                        "Transcribe exactly what the user said in English. "
                        "Output only the transcription, nothing else."
                    )},
                ]
            }]

            inputs = self.processor.apply_chat_template(
                messages,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
                add_generation_prompt=True,
            ).to(self.model.device)
            input_len = inputs["input_ids"].shape[-1]

            with torch.no_grad():
                outputs = self.model.generate(**inputs, max_new_tokens=200, do_sample=False)

            text = self.processor.decode(outputs[0][input_len:], skip_special_tokens=True).strip()
            log.info("Transcription result: %r", text)
            return text
        except Exception as e:
            log.error("Transcription failed: %s", e)
            self.on_error(f"Transcription error: {e}")
            return ""
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    # --------------------------------------------------------------- LLM (Gemma 4 text generation)
    @staticmethod
    def _trim_to_last_sentence(text: str) -> str:
        if text and text[-1] in ".!?\"')\u2019":
            return text
        for i in range(len(text) - 1, -1, -1):
            if text[i] in ".!?":
                return text[: i + 1]
        return text

    @staticmethod
    def _format_messages(messages: list) -> list:
        """Convert plain-string messages to the content-list format Gemma 4 expects."""
        formatted = []
        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                formatted.append({
                    "role": msg["role"],
                    "content": [{"type": "text", "text": content}],
                })
            else:
                formatted.append(msg)
        return formatted

    def query_llm(self, user_text: str) -> str:
        """Generate a response using the conversation history."""
        import torch

        log.info("User input: %r", user_text)
        self.messages.append({"role": "user", "content": user_text})

        if self.model is None:
            err = "Model not loaded"
            self.on_error(err)
            return err

        try:
            inputs = self.processor.apply_chat_template(
                self._format_messages(self.messages),
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
                add_generation_prompt=True,
            ).to(self.model.device)
            input_len = inputs["input_ids"].shape[-1]

            llm = self.settings["llm"]
            temp = llm["temperature"]

            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=llm["num_predict"],
                    do_sample=temp > 0,
                    temperature=temp if temp > 0 else None,
                )

            reply = self.processor.decode(outputs[0][input_len:], skip_special_tokens=True).strip()

            raw_reply = reply
            reply = self._trim_to_last_sentence(reply)
            if reply != raw_reply:
                log.warning("Trimmed truncated response: %r -> %r", raw_reply, reply)
            log.info("LLM reply: %r", reply)

            self.messages.append({"role": "assistant", "content": reply})
            return reply
        except Exception as e:
            err = f"Generation error: {e}"
            log.error("LLM query failed: %s", e)
            self.on_error(err)
            return err

    # --------------------------------------------------------------- TTS
    def speak(self, text: str):
        if not text or text.startswith("[") or self.tts is None:
            return
        clean = text.replace("...", ",").replace(";", ",")
        clean = re.sub(r'\ba\b', 'uh', clean)
        clean = re.sub(r"[^a-zA-Z0-9\s.,!?'\-:;\"\(\)]", "", clean)
        log.debug("TTS input: %r", clean)

        # Mute the mic while speaking so VAD doesn't capture TTS output
        was_listening = self.listening
        if was_listening:
            self.stop_listening()

        try:
            audio = self.tts.generate_speech_audio(clean)
            volume = self.settings["audio"].get("volume", 1.0)
            if volume != 1.0:
                audio = audio * volume
            sd.play(audio, self.tts.rate)
            sd.wait()
        except Exception as e:
            log.error("TTS error: %s", e)
            self.on_error(f"TTS error: {e}")
        finally:
            if was_listening:
                self.start_listening()

    def stop_speaking(self):
        sd.stop()

    # --------------------------------------------------------------- worker
    def _worker_loop(self):
        while self.running:
            try:
                task = self._worker_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                task()
            except Exception as e:
                self.on_error(str(e))

    def submit(self, fn):
        self._worker_queue.put(fn)

    # --------------------------------------------------------------- convenience
    def process_speech(self, audio: np.ndarray):
        duration = len(audio) / self._sr
        self.on_status(f"Transcribing ({duration:.1f}s)")
        user_text = self.transcribe(audio)
        if not user_text:
            self.on_status("Listening")
            self.on_error("Couldn't understand — try again")
            return
        self.on_message("user", user_text)
        self.on_status("Thinking")
        reply = self.query_llm(user_text)
        if reply.startswith(("Generation error:", "Connection error:", "Model not loaded")):
            self.on_message("assistant", f"[{reply}]")
        else:
            self.on_message("assistant", reply)
            self.on_status("Speaking")
            self.speak(reply + " ")
        self.on_status("Listening")

    def process_text(self, text: str):
        self.on_message("user", text)
        self.on_status("Thinking")
        reply = self.query_llm(text)
        if reply.startswith(("Generation error:", "Connection error:", "Model not loaded")):
            self.on_message("assistant", f"[{reply}]")
        else:
            self.on_message("assistant", reply)
            self.on_status("Speaking")
            self.speak(reply + " ")
        self.on_status("Listening")

    def clear_history(self):
        self.messages = [
            {"role": "system", "content": self.settings["general"]["system_prompt"]}
        ]

    # --------------------------------------------------------------- audio devices
    @staticmethod
    def get_input_devices() -> list:
        devices = sd.query_devices()
        result = []
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                result.append((i, d["name"]))
        return result
