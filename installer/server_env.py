from __future__ import annotations

from pathlib import Path


ENV_KEY_ORDER = [
    "TELEGRAM_TOKEN",
    "DB_PASSWORD",
    "AIYA_ADMIN_TOKEN",
    "AIYA_EXTRA_ADMIN_TOKENS",
    "HOST_CONTROL_TOKEN",
    "ENABLE_TTS",
    "ENABLE_OCR",
    "ENABLE_IMAGE_GENERATION",
    "ENABLE_DESKTOP_SUBTITLES",
    "ENABLE_EMOJI",
    "ENABLE_SCREEN_CONTEXT",
    "ENABLE_GAME_MODE",
    "ENABLE_VISION",
    "ENABLE_WIKI",
    "AIYA_PERFORMANCE_PROFILE",
    "AIYA_HARDWARE_CLASS",
    "AIYA_LLM_MODE",
    "AIYA_LLM_PROVIDER",
    "AIYA_LLM_BASE_URL",
    "AIYA_LLM_API_KEY",
    "OLLAMA_CHAT_MODEL",
    "OLLAMA_EMBED_MODEL",
    "OLLAMA_VISION_MODEL",
    "AIYA_TRANSLATION_MODEL",
    "TTS_BACKEND_URL",
    "TRANSLATION_BACKEND_URL",
    "AIYA_ALLOW_LOCAL_TTS",
    "IMAGE_BACKEND_URL",
    "AIYA_TTS_PROVIDER",
    "AIYA_TTS_PRESET",
    "TTS_VOICE",
    "AIYA_TTS_RATE",
    "AIYA_TTS_PITCH",
    "OLLAMA_IMAGE",
    "OLLAMA_HOST",
    "HOST_CONTROL_URL",
]

ENV_DEFAULTS = {
    "TELEGRAM_TOKEN": "",
    "DB_PASSWORD": "",
    "AIYA_ADMIN_TOKEN": "",
    "AIYA_EXTRA_ADMIN_TOKENS": "",
    "HOST_CONTROL_TOKEN": "",
    "ENABLE_TTS": "true",
    "ENABLE_OCR": "false",
    "ENABLE_IMAGE_GENERATION": "false",
    "ENABLE_DESKTOP_SUBTITLES": "true",
    "ENABLE_EMOJI": "true",
    "ENABLE_SCREEN_CONTEXT": "true",
    "ENABLE_GAME_MODE": "true",
    "ENABLE_VISION": "true",
    "ENABLE_WIKI": "true",
    "AIYA_PERFORMANCE_PROFILE": "balanced",
    "AIYA_HARDWARE_CLASS": "",
    "AIYA_LLM_MODE": "bundled_ollama",
    "AIYA_LLM_PROVIDER": "ollama",
    "AIYA_LLM_BASE_URL": "",
    "AIYA_LLM_API_KEY": "",
    "OLLAMA_CHAT_MODEL": "",
    "OLLAMA_EMBED_MODEL": "",
    "OLLAMA_VISION_MODEL": "",
    "AIYA_TRANSLATION_MODEL": "",
    "TTS_BACKEND_URL": "",
    "TRANSLATION_BACKEND_URL": "",
    "AIYA_ALLOW_LOCAL_TTS": "false",
    "IMAGE_BACKEND_URL": "",
    "AIYA_TTS_PROVIDER": "edge",
    "AIYA_TTS_PRESET": "balanced_uk",
    "TTS_VOICE": "uk-UA-PolinaNeural",
    "AIYA_TTS_RATE": "+0%",
    "AIYA_TTS_PITCH": "+0Hz",
    "OLLAMA_IMAGE": "ollama/ollama:latest",
    "OLLAMA_HOST": "http://ollama:11434",
    "HOST_CONTROL_URL": "http://host.docker.internal:8765",
}


def read_server_env(target_dir: Path) -> dict[str, str]:
    env_path = target_dir / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _as_env_bool(value: object, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return str(value).lower()
    text = str(value).strip().lower()
    if not text:
        return default
    return "true" if text in {"1", "true", "yes", "on"} else "false"


def build_server_env_values(config: dict, existing: dict[str, str] | None = None) -> dict[str, str]:
    values = dict(ENV_DEFAULTS)
    if existing:
        values.update(existing)

    llm_mode = (config.get("llm_mode") or values.get("AIYA_LLM_MODE") or "bundled_ollama").strip()
    llm_provider = "ollama"
    ollama_host = values.get("OLLAMA_HOST", ENV_DEFAULTS["OLLAMA_HOST"]).strip() or ENV_DEFAULTS["OLLAMA_HOST"]
    llm_base_url = values.get("AIYA_LLM_BASE_URL", "")
    llm_api_key = values.get("AIYA_LLM_API_KEY", "")
    if llm_mode == "external_ollama":
        ollama_host = config.get("external_ollama_url", "").strip() or ollama_host or "http://host.docker.internal:11434"
        llm_base_url = ""
        llm_api_key = ""
    elif llm_mode == "external_api":
        llm_provider = "openai_compatible"
        llm_base_url = config.get("external_api_url", "").strip() or llm_base_url
        llm_api_key = config.get("external_api_key", "").strip() or llm_api_key
    else:
        ollama_host = "http://ollama:11434"
        llm_base_url = ""
        llm_api_key = ""

    values.update(
        {
            "TELEGRAM_TOKEN": config.get("telegram_token", values.get("TELEGRAM_TOKEN", "")).strip(),
            "DB_PASSWORD": config.get("db_password", values.get("DB_PASSWORD", "")).strip(),
            "AIYA_ADMIN_TOKEN": config.get("admin_token", values.get("AIYA_ADMIN_TOKEN", "")).strip(),
            "AIYA_EXTRA_ADMIN_TOKENS": config.get("extra_admin_tokens", values.get("AIYA_EXTRA_ADMIN_TOKENS", "")).strip(),
            "HOST_CONTROL_TOKEN": config.get("host_control_token", values.get("HOST_CONTROL_TOKEN", "")).strip(),
            "ENABLE_TTS": _as_env_bool(config.get("enable_tts"), values.get("ENABLE_TTS", ENV_DEFAULTS["ENABLE_TTS"])),
            "ENABLE_OCR": _as_env_bool(config.get("enable_ocr"), values.get("ENABLE_OCR", ENV_DEFAULTS["ENABLE_OCR"])),
            "ENABLE_IMAGE_GENERATION": _as_env_bool(
                config.get("enable_image_generation"),
                values.get("ENABLE_IMAGE_GENERATION", ENV_DEFAULTS["ENABLE_IMAGE_GENERATION"]),
            ),
            "ENABLE_VISION": _as_env_bool(config.get("enable_vision"), values.get("ENABLE_VISION", ENV_DEFAULTS["ENABLE_VISION"])),
            "AIYA_PERFORMANCE_PROFILE": (config.get("performance_profile") or values.get("AIYA_PERFORMANCE_PROFILE") or "balanced").strip(),
            "AIYA_HARDWARE_CLASS": (config.get("hardware_class") or values.get("AIYA_HARDWARE_CLASS") or "").strip(),
            "AIYA_LLM_MODE": llm_mode,
            "AIYA_LLM_PROVIDER": llm_provider,
            "AIYA_LLM_BASE_URL": llm_base_url,
            "AIYA_LLM_API_KEY": llm_api_key,
            "OLLAMA_CHAT_MODEL": (config.get("chat_model") or values.get("OLLAMA_CHAT_MODEL") or "").strip(),
            "OLLAMA_EMBED_MODEL": (config.get("embed_model") or values.get("OLLAMA_EMBED_MODEL") or "").strip(),
            "OLLAMA_VISION_MODEL": (config.get("vision_model") or values.get("OLLAMA_VISION_MODEL") or "").strip(),
            "AIYA_TRANSLATION_MODEL": (config.get("translation_model") or values.get("AIYA_TRANSLATION_MODEL") or "").strip(),
            "AIYA_TTS_PROVIDER": (config.get("tts_provider") or values.get("AIYA_TTS_PROVIDER") or "edge").strip(),
            "AIYA_TTS_PRESET": (config.get("tts_preset") or values.get("AIYA_TTS_PRESET") or "balanced_uk").strip(),
            "TTS_VOICE": (config.get("tts_voice") or values.get("TTS_VOICE") or "uk-UA-PolinaNeural").strip(),
            "AIYA_TTS_RATE": (config.get("tts_rate") or values.get("AIYA_TTS_RATE") or "+0%").strip(),
            "AIYA_TTS_PITCH": (config.get("tts_pitch") or values.get("AIYA_TTS_PITCH") or "+0Hz").strip(),
            "OLLAMA_HOST": ollama_host,
        }
    )
    return values


def write_server_env(target_dir: Path, config: dict):
    values = build_server_env_values(config, existing=read_server_env(target_dir))
    extra_keys = sorted(key for key in values if key not in ENV_KEY_ORDER)
    ordered_keys = [*ENV_KEY_ORDER, *extra_keys]
    lines = [f"{key}={values.get(key, '')}" for key in ordered_keys]
    (target_dir / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
