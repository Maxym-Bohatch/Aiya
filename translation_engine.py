import json

import requests

from config import settings

OLLAMA_GENERATE = f"{settings.ollama_host}/api/generate"


def translate_text(text: str, source_lang: str = "auto", target_lang: str = "uk") -> dict:
    normalized = (text or "").strip()
    if not normalized:
        return {"ok": False, "message": "Text is empty.", "translation": ""}

    prompt = (
        "You are a local translation engine. "
        f"Translate the text from {source_lang} to {target_lang}. "
        "Return only the translated text, preserve line breaks, do not explain anything, "
        "do not add quotes, and keep UI/game text concise.\n\n"
        f"TEXT:\n{normalized}"
    )
    payload = {
        "model": settings.ollama_chat_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
        },
    }
    try:
        response = requests.post(OLLAMA_GENERATE, json=payload, timeout=settings.performance.llm_timeout_seconds)
        response.raise_for_status()
        translated = (response.json().get("response") or "").strip()
        return {"ok": bool(translated), "translation": translated, "source_lang": source_lang, "target_lang": target_lang}
    except Exception as exc:
        return {"ok": False, "message": f"Translation failed: {exc}", "translation": ""}
