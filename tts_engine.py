import math
import os
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

from config import settings


def _fallback_wave(text: str, out_path: str):
    sample_rate = 22050
    base = 233
    fib = [1, 2, 3, 5, 8, 13]
    duration = max(1.4, min(8.0, len(text) * 0.08))
    total_frames = int(sample_rate * duration)
    amplitude = 10000

    with wave.open(out_path, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for i in range(total_frames):
            t = i / sample_rate
            freq = base + fib[(i // 3770) % len(fib)] * 16
            shimmer = math.sin(2 * math.pi * (5 + fib[(i // 6100) % len(fib)] * 0.35) * t) * 7
            overtone = math.sin(2 * math.pi * (freq * 2.0) * t) * 0.12
            sample = int(amplitude * (math.sin(2 * math.pi * (freq + shimmer) * t) + overtone))
            wav_file.writeframes(struct.pack("<h", sample))


def synthesize_to_wav(text: str) -> str:
    text = (text or "").strip() or "..."
    output_dir = Path(tempfile.gettempdir()) / "aiya_tts"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"aiya_{next(tempfile._get_candidate_names())}.wav"

    fib = [1, 2, 3, 5, 8, 13]
    rate = 148 + fib[len(text) % len(fib)] * 3
    pitch = 68 + fib[(len(text) + 2) % len(fib)] * 2
    word_gap = 2 + fib[(len(text) + 1) % len(fib)]
    amplitude = 120 + fib[(len(text) + 3) % len(fib)] * 2
    voice = os.getenv("TTS_VOICE", "uk+f3")

    try:
        subprocess.run(
            [
                "espeak-ng",
                "-v",
                voice,
                "-s",
                str(rate),
                "-p",
                str(pitch),
                "-g",
                str(word_gap),
                "-a",
                str(amplitude),
                "-w",
                str(out_path),
                text,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        _fallback_wave(text, str(out_path))

    return str(out_path)


def tts_capabilities():
    return {
        "voice_style": "young-feminine",
        "voice": os.getenv("TTS_VOICE", "uk+f3"),
        "desktop_palette": "white-green",
        "enabled": settings.enable_tts,
    }
