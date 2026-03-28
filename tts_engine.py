import asyncio
import base64
import math
import os
import re
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

import requests

from config import settings

try:
    import edge_tts
except Exception:
    edge_tts = None

try:
    from gtts import gTTS
except Exception:
    gTTS = None


VOICE_PRESETS = {
    "balanced_uk": {
        "label": "Balanced Ukrainian",
        "provider": "edge",
        "voice": "uk-UA-PolinaNeural",
        "rate": "+0%",
        "pitch": "+0Hz",
    },
    "soft_uk": {
        "label": "Soft Ukrainian",
        "provider": "edge",
        "voice": "uk-UA-PolinaNeural",
        "rate": "-12%",
        "pitch": "-8Hz",
    },
    "bright_uk": {
        "label": "Bright Ukrainian",
        "provider": "edge",
        "voice": "uk-UA-PolinaNeural",
        "rate": "+6%",
        "pitch": "+10Hz",
    },
    "warm_en": {
        "label": "Warm English",
        "provider": "edge",
        "voice": "en-US-JennyNeural",
        "rate": "-4%",
        "pitch": "-4Hz",
    },
    "clear_en": {
        "label": "Clear English",
        "provider": "edge",
        "voice": "en-US-AriaNeural",
        "rate": "+2%",
        "pitch": "+0Hz",
    },
}


def resolve_tts_settings() -> dict[str, str]:
    preset = VOICE_PRESETS.get(settings.tts_preset, VOICE_PRESETS["balanced_uk"])
    return {
        "preset": settings.tts_preset if settings.tts_preset in VOICE_PRESETS else "balanced_uk",
        "provider": (settings.tts_provider or preset["provider"]).strip().lower(),
        "voice": (settings.tts_voice or preset["voice"]).strip(),
        "rate": (settings.tts_rate or preset["rate"]).strip(),
        "pitch": (settings.tts_pitch or preset["pitch"]).strip(),
    }


def voice_delivery_enabled() -> bool:
    if settings.tts_backend_url:
        return True
    if settings.tts_provider == "edge" and edge_tts is not None:
        return True
    if gTTS is not None:
        return True
    return os.getenv("AIYA_ALLOW_LOCAL_TTS", "").strip().lower() in {"1", "true", "yes", "on"}


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
        for index in range(total_frames):
            moment = index / sample_rate
            freq = base + fib[(index // 3770) % len(fib)] * 16
            shimmer = math.sin(2 * math.pi * (5 + fib[(index // 6100) % len(fib)] * 0.35) * moment) * 7
            overtone = math.sin(2 * math.pi * (freq * 2.0) * moment) * 0.12
            sample = int(amplitude * (math.sin(2 * math.pi * (freq + shimmer) * moment) + overtone))
            wav_file.writeframes(struct.pack("<h", sample))


def _prepare_output_path(suffix: str) -> Path:
    output_dir = Path(tempfile.gettempdir()) / "aiya_tts"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"aiya_{next(tempfile._get_candidate_names())}{suffix}"


def _sanitize_text(text: str) -> str:
    text = (text or "").strip() or "..."
    text = re.sub(r"http[s]?://\S+", "", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s.,!?;:()\-'\"/%]", " ", text, flags=re.UNICODE)
    return text[:900].strip() or "..."


def _guess_audio_format(content_type: str) -> tuple[str, str]:
    lowered = (content_type or "").lower()
    if "ogg" in lowered:
        return ".ogg", "audio/ogg"
    if "mpeg" in lowered or "mp3" in lowered:
        return ".mp3", "audio/mpeg"
    return ".wav", "audio/wav"


def _write_backend_audio(response: requests.Response) -> tuple[str, str, str]:
    suffix, media_type = _guess_audio_format(response.headers.get("Content-Type", ""))
    out_path = _prepare_output_path(suffix)
    out_path.write_bytes(response.content)
    return str(out_path), media_type, out_path.name


def _write_backend_json(payload: dict) -> tuple[str, str, str]:
    audio_b64 = (payload.get("audio_base64") or "").strip()
    if not audio_b64:
        raise RuntimeError("TTS backend JSON response does not include audio_base64.")
    audio_format = (payload.get("format") or "wav").strip().lower()
    media_type = payload.get("media_type") or {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "ogg": "audio/ogg",
    }.get(audio_format, "application/octet-stream")
    suffix = "." + audio_format.lstrip(".")
    out_path = _prepare_output_path(suffix)
    out_path.write_bytes(base64.b64decode(audio_b64))
    return str(out_path), media_type, out_path.name


def _synthesize_via_backend(text: str) -> tuple[str, str, str]:
    response = requests.post(settings.tts_backend_url, json={"text": text}, timeout=180)
    response.raise_for_status()
    content_type = (response.headers.get("Content-Type") or "").lower()
    if content_type.startswith("audio/"):
        return _write_backend_audio(response)
    return _write_backend_json(response.json())


async def _edge_save(text: str, out_path: Path):
    resolved = resolve_tts_settings()
    communicate = edge_tts.Communicate(
        text,
        voice=resolved["voice"] or "uk-UA-PolinaNeural",
        rate=resolved["rate"] or "+0%",
        pitch=resolved["pitch"] or "+0Hz",
    )
    await communicate.save(str(out_path))


def _synthesize_via_edge(text: str) -> tuple[str, str, str]:
    if edge_tts is None:
        raise RuntimeError("edge-tts is not installed.")
    out_path = _prepare_output_path(".mp3")
    asyncio.run(_edge_save(text, out_path))
    return str(out_path), "audio/mpeg", out_path.name


def _gtts_language() -> str:
    voice = resolve_tts_settings()["voice"].lower()
    if voice.startswith("uk-") or voice.startswith("uk_") or voice.startswith("uk"):
        return "uk"
    if voice.startswith("pl-") or voice.startswith("pl"):
        return "pl"
    if voice.startswith("ru-") or voice.startswith("ru"):
        return "ru"
    return "en"


def _synthesize_via_gtts(text: str) -> tuple[str, str, str]:
    if gTTS is None:
        raise RuntimeError("gTTS is not installed.")
    out_path = _prepare_output_path(".mp3")
    gTTS(text=text, lang=_gtts_language(), slow=False).save(str(out_path))
    return str(out_path), "audio/mpeg", out_path.name


def synthesize_to_wav(text: str) -> str:
    audio_path, _, _ = synthesize_to_audio_file(text)
    return audio_path


def synthesize_to_audio_file(text: str) -> tuple[str, str, str]:
    prepared = _sanitize_text(text)
    resolved = resolve_tts_settings()

    if settings.tts_backend_url:
        try:
            return _synthesize_via_backend(prepared)
        except Exception as exc:
            print(f"TTS backend error: {exc}")

    if resolved["provider"] == "edge":
        try:
            return _synthesize_via_edge(prepared)
        except Exception as exc:
            print(f"Edge TTS error: {exc}")
    try:
        return _synthesize_via_gtts(prepared)
    except Exception as exc:
        print(f"gTTS error: {exc}")

    if not voice_delivery_enabled():
        raise RuntimeError(
            "High-quality TTS is not configured. Set TTS_BACKEND_URL, keep AIYA_TTS_PROVIDER=edge, or explicitly allow the local fallback."
        )

    out_path = _prepare_output_path(".wav")
    fib = [1, 2, 3, 5, 8, 13]
    rate = 136 + fib[len(prepared) % len(fib)] * 2
    pitch = 54 + fib[(len(prepared) + 2) % len(fib)] * 2
    word_gap = 3 + fib[(len(prepared) + 1) % len(fib)]
    amplitude = 115 + fib[(len(prepared) + 3) % len(fib)] * 2
    voice = resolved["voice"] or "uk"

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
                prepared,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        _fallback_wave(prepared, str(out_path))

    return str(out_path), "audio/wav", out_path.name


def tts_capabilities():
    resolved = resolve_tts_settings()
    return {
        "voice_style": "young-feminine",
        "voice": resolved["voice"],
        "desktop_palette": "white-green",
        "enabled": bool(settings.enable_tts or settings.tts_backend_url),
        "delivery_enabled": voice_delivery_enabled(),
        "backend_url": bool(settings.tts_backend_url),
        "provider": resolved["provider"],
        "rate": resolved["rate"],
        "pitch": resolved["pitch"],
        "preset": resolved["preset"],
        "presets": {key: value["label"] for key, value in VOICE_PRESETS.items()},
        "edge_available": edge_tts is not None,
        "gtts_available": gTTS is not None,
    }
