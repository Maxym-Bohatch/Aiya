import requests

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

from config import settings

OLLAMA_GENERATE = f"{settings.ollama_host}/api/generate"


def _normalize_lang(value: str, fallback: str) -> str:
    cleaned = (value or "").strip()
    return cleaned or fallback


def _translate_via_backend(text: str, source_lang: str, target_lang: str) -> dict:
    response = requests.post(
        settings.translation_backend_url,
        json={
            "text": text,
            "source_language": source_lang,
            "target_language": target_lang,
        },
        timeout=settings.performance.llm_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    translated = (payload.get("translation") or payload.get("translated_text") or "").strip()
    return {
        "ok": bool(translated),
        "translation": translated,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "provider": "backend",
    }


def _translate_via_ollama(text: str, source_lang: str, target_lang: str) -> dict:
    prompt = (
        "You are a precise game and UI translator.\n"
        f"Translate from {source_lang} to {target_lang}.\n"
        "Rules:\n"
        "- Return only the translated text.\n"
        "- Preserve line breaks when possible.\n"
        "- Keep names, hotkeys, and button labels recognizable.\n"
        "- Do not explain anything.\n"
        "- Do not add quotes.\n"
        "- Fix obvious OCR glitches only when the intended meaning is clear.\n\n"
        f"TEXT:\n{text}"
    )
    payload = {
        "model": settings.translation_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.05,
            "top_p": 0.9,
        },
    }
    response = requests.post(
        OLLAMA_GENERATE,
        json=payload,
        timeout=settings.performance.llm_timeout_seconds,
    )
    response.raise_for_status()
    translated = (response.json().get("response") or "").strip()
    return {
        "ok": bool(translated),
        "translation": translated,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "provider": "ollama",
        "model": settings.translation_model,
    }


def _translate_via_google(text: str, source_lang: str, target_lang: str) -> dict:
    if GoogleTranslator is None:
        raise RuntimeError("deep-translator is not installed.")
    source = "auto" if source_lang == "auto" else source_lang
    translated = GoogleTranslator(source=source, target=target_lang).translate(text)
    return {
        "ok": bool(translated),
        "translation": (translated or "").strip(),
        "source_lang": source_lang,
        "target_lang": target_lang,
        "provider": "google",
    }


def translate_text(text: str, source_lang: str = "auto", target_lang: str = "uk") -> dict:
    normalized = (text or "").strip()
    if not normalized:
        return {"ok": False, "message": "Text is empty.", "translation": ""}

    source_lang = _normalize_lang(source_lang, "auto")
    target_lang = _normalize_lang(target_lang, "uk")
    if source_lang != "auto" and source_lang.lower() == target_lang.lower():
        return {
            "ok": True,
            "translation": normalized,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "provider": "passthrough",
        }

    try:
        if settings.translation_backend_url:
            return _translate_via_backend(normalized, source_lang, target_lang)
        if GoogleTranslator is not None:
            try:
                result = _translate_via_google(normalized, source_lang, target_lang)
                if result.get("translation"):
                    return result
            except Exception:
                pass
        result = _translate_via_ollama(normalized, source_lang, target_lang)
        translated = (result.get("translation") or "").strip()
        if translated and translated.lower() != normalized.lower():
            return result
        return {
            "ok": True,
            "translation": translated or normalized,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "provider": result.get("provider", "ollama"),
            "model": result.get("model", settings.translation_model),
        }
    except Exception as exc:
        return {"ok": False, "message": f"Translation failed: {exc}", "translation": ""}
