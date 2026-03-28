from __future__ import annotations

from pathlib import Path


def write_server_env(target_dir: Path, config: dict):
    llm_mode = config.get("llm_mode", "bundled_ollama")
    llm_provider = "ollama"
    ollama_host = "http://ollama:11434"
    llm_base_url = ""
    llm_api_key = ""
    if llm_mode == "external_ollama":
        ollama_host = config.get("external_ollama_url", "").strip() or "http://host.docker.internal:11434"
    elif llm_mode == "external_api":
        llm_provider = "openai_compatible"
        llm_base_url = config.get("external_api_url", "").strip()
        llm_api_key = config.get("external_api_key", "").strip()

    lines = [
        f"TELEGRAM_TOKEN={config.get('telegram_token', '')}",
        f"DB_PASSWORD={config.get('db_password', '')}",
        f"AIYA_ADMIN_TOKEN={config.get('admin_token', '')}",
        f"AIYA_EXTRA_ADMIN_TOKENS={config.get('extra_admin_tokens', '')}",
        f"HOST_CONTROL_TOKEN={config.get('host_control_token', '')}",
        "",
        f"ENABLE_TTS={str(config.get('enable_tts', True)).lower()}",
        f"ENABLE_OCR={str(config.get('enable_ocr', False)).lower()}",
        f"ENABLE_IMAGE_GENERATION={str(config.get('enable_image_generation', False)).lower()}",
        "ENABLE_DESKTOP_SUBTITLES=true",
        "ENABLE_EMOJI=true",
        "ENABLE_SCREEN_CONTEXT=true",
        "ENABLE_GAME_MODE=true",
        f"ENABLE_VISION={str(config.get('enable_vision', True)).lower()}",
        "ENABLE_WIKI=true",
        "",
        f"AIYA_PERFORMANCE_PROFILE={config.get('performance_profile', 'balanced')}",
        f"AIYA_HARDWARE_CLASS={config.get('hardware_class', '')}",
        f"AIYA_LLM_MODE={llm_mode}",
        f"AIYA_LLM_PROVIDER={llm_provider}",
        f"AIYA_LLM_BASE_URL={llm_base_url}",
        f"AIYA_LLM_API_KEY={llm_api_key}",
        "",
        f"OLLAMA_CHAT_MODEL={config.get('chat_model', '')}",
        f"OLLAMA_EMBED_MODEL={config.get('embed_model', '')}",
        f"OLLAMA_VISION_MODEL={config.get('vision_model', '')}",
        f"AIYA_TRANSLATION_MODEL={config.get('translation_model', '')}",
        "",
        "TTS_BACKEND_URL=",
        "TRANSLATION_BACKEND_URL=",
        "AIYA_ALLOW_LOCAL_TTS=false",
        "IMAGE_BACKEND_URL=",
        "AIYA_TTS_PROVIDER=edge",
        f"AIYA_TTS_PRESET={config.get('tts_preset', 'balanced_uk')}",
        f"TTS_VOICE={config.get('tts_voice', 'uk-UA-PolinaNeural')}",
        f"AIYA_TTS_RATE={config.get('tts_rate', '+0%')}",
        f"AIYA_TTS_PITCH={config.get('tts_pitch', '+0Hz')}",
        "",
        "OLLAMA_IMAGE=ollama/ollama:latest",
        f"OLLAMA_HOST={ollama_host}",
        "HOST_CONTROL_URL=http://host.docker.internal:8765",
    ]
    (target_dir / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
