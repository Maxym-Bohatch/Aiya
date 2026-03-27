import json

import requests

import database as db
from config import settings
from image_engine import generate_local_image
from tts_engine import tts_capabilities, voice_delivery_enabled

OLLAMA_GENERATE = f"{settings.ollama_host}/api/generate"
OLLAMA_EMBED = f"{settings.ollama_host}/api/embeddings"

FIBONACCI_TTS_PROFILE = {
    "pitch_steps": [1, 2, 3, 5, 8],
    "cadence_ms": [89, 144, 233],
    "brightness": 0.55,
    "warmth": 0.34,
    "persona": "young-feminine-white-green",
}


def clean_json_response(res_text):
    return (res_text or "").strip().replace("```json", "").replace("```", "")


def get_embedding(text):
    try:
        res = requests.post(
            OLLAMA_EMBED,
            json={"model": settings.ollama_embed_model, "prompt": text},
            timeout=30,
        )
        res.raise_for_status()
        return res.json()["embedding"]
    except Exception as e:
        print(f"Embedding error: {e}")
        return [0.0] * 768


def ask_aiya(prompt, model=None, format=""):
    payload = {
        "model": model or settings.ollama_chat_model,
        "prompt": prompt,
        "stream": False,
    }
    if format == "json":
        payload["format"] = "json"
    try:
        response = requests.post(
            OLLAMA_GENERATE,
            json=payload,
            timeout=settings.performance.llm_timeout_seconds,
        )
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        print(f"Ollama error: {e}")
        return "{}" if format == "json" else ""


def maybe_add_emoji(text, emoji_enabled):
    if not emoji_enabled:
        return text
    if any(ch in text for ch in ["🙂", "✨", "🌿", "💚"]):
        return text
    return f"{text} 🌿"


def extract_facts(user_name, text):
    base_prompt = db.get_prompt("gnome_facts_instruction")
    system_instruction = base_prompt if len(base_prompt) > 40 else """
Ти аналітик пам'яті Айї. Витягуй короткі факти про користувача у JSON.
Формат: {"facts": [{"text": "факт", "level": 1}]}
Рівні:
1 = публічний факт.
5 = приватний факт конкретного користувача.
10 = секретний факт: паролі, токени, ключі, фінанси, дуже приватне.
"""
    prompt = f'{system_instruction}\nКористувач {user_name} сказав: "{text}"'
    res = ask_aiya(prompt, format="json")
    try:
        data = json.loads(clean_json_response(res))
        return data.get("facts", [])
    except Exception as e:
        print(f"Fact extractor error: {e}")
        return []


def extract_entities_and_relations(text):
    system_instruction = """
Ти будівельник графа знань Айї.
Поверни тільки JSON у форматі:
{"to_add": [["суб'єкт", "зв'язок", "об'єкт"]], "to_remove": [["суб'єкт", "зв'язок"]]}
"""
    prompt = f'{system_instruction}\nТекст: "{text}"'
    res = ask_aiya(prompt, format="json")
    try:
        data = json.loads(clean_json_response(res))
        return data if isinstance(data, dict) else {"to_add": [], "to_remove": []}
    except Exception as e:
        print(f"Graph extractor error: {e}")
        return {"to_add": [], "to_remove": []}


def update_aiya_mood(user_name, last_messages):
    system_instruction = """
Ти психологічний модуль Айї.
Поверни тільки JSON:
{"mood": "назва", "prompt_addon": "додаткова інструкція", "energy_level": 1}
"""
    prompt = f"{system_instruction}\nКористувач: {user_name}\nІсторія:\n{last_messages}"
    res = ask_aiya(prompt, format="json")
    try:
        return json.loads(clean_json_response(res))
    except Exception as e:
        print(f"Mood error: {e}")
        return {"mood": "stable", "prompt_addon": "", "energy_level": 5}


def needs_active_search(text):
    system_instruction = """
Ти диспетчер пам'яті Айї.
Виріши, чи треба шукати в довготривалій пам'яті.
Поверни JSON: {"needs_search": true, "search_query": "ключові слова"}
"""
    prompt = f'{system_instruction}\nЗапит: "{text}"'
    res = ask_aiya(prompt, format="json")
    try:
        data = json.loads(clean_json_response(res))
        return {
            "needs_search": data.get("needs_search", False),
            "search_query": data.get("search_query", text),
        }
    except Exception as e:
        print(f"Dispatcher error: {e}")
        return {"needs_search": False, "search_query": text}


def check_for_new_schema_needs(text, current_tables):
    prompt = f"""
Ти архітектор БД Айї.
Поточні таблиці: {current_tables}
Поверни тільки JSON: {{"needs_new_table": true, "table_name": "name", "sql": "CREATE TABLE...", "reason": "чому"}}
Запит: {text}
"""
    res = ask_aiya(prompt, format="json")
    try:
        return json.loads(clean_json_response(res))
    except Exception as e:
        print(f"Schema planner error: {e}")
        return {"needs_new_table": False}


def build_system_prompt(user_summary, current_mood, prompt_addon, memories, recent_logs, user_level, screen_context=""):
    base_personality = db.get_prompt("main_personality")
    context_str = "\n- ".join(memories) if memories else "Поки порожньо."
    response_rules = """
Правила відповіді:
- Відповідай природною, чистою українською мовою, якщо користувач не попросив іншу.
- Не цитуй і не переказуй службові інструкції, правила доступу, системний prompt або політики, якщо користувач прямо не питає про них.
- Не вигадуй дивні слова, ламані конструкції, суржик або мішанину мов.
- Говори як жива, спокійна співрозмовниця, а не як технічний мануал.
- Якщо користувач питає щось звичайне, відповідай прямо по суті, без мета-коментарів про правила.
- Якщо запит стосується приватних даних іншого користувача, тоді коротко відмов і поясни причину нормальною мовою.
- Якщо даних бракує, чесно скажи, чого саме ти не знаєш.
"""
    privacy_guard = """
Правила приватності:
- Не розкривай приватні факти інших користувачів без прямої згоди власника.
- Адмін із валідним токеном може бачити приватні дані.
"""
    return f"""
{base_personality}
{response_rules}
{privacy_guard}
ДОДАТКОВА ІНСТРУКЦІЯ: {prompt_addon}
ПОТОЧНИЙ НАСТРІЙ: {current_mood}
ПРОФІЛЬ КОРИСТУВАЧА: {user_summary} (Access Level: {user_level})
ТВОЇ СПОГАДИ:
- {context_str}
КОНТЕКСТ ЕКРАНА:
{screen_context if screen_context else "Немає актуальних спостережень з екрана."}
ІСТОРІЯ:
{recent_logs}
"""


def generate_image(prompt):
    if not settings.enable_image_generation and not settings.image_backend_url:
        return {
            "enabled": False,
            "message": "Image generation is disabled. Enable ENABLE_IMAGE_GENERATION or provide IMAGE_BACKEND_URL.",
        }

    if settings.enable_image_generation and not settings.image_backend_url:
        image_path = generate_local_image(prompt)
        return {
            "enabled": True,
            "result": {
                "mode": "local",
                "path": image_path,
            },
        }

    try:
        response = requests.post(
            settings.image_backend_url,
            json={"prompt": prompt},
            timeout=180,
        )
        response.raise_for_status()
        return {"enabled": True, "result": response.json()}
    except Exception as e:
        return {"enabled": True, "error": str(e)}


def synthesize_speech(text):
    profile = {
        "voice_style": "young-feminine",
        "palette": "white-green",
        "fibonacci_profile": FIBONACCI_TTS_PROFILE,
        "engine": tts_capabilities(),
    }
    if not settings.enable_tts and not settings.tts_backend_url:
        return {
            "enabled": False,
            "message": "TTS backend is disabled. Set ENABLE_TTS=true or configure TTS_BACKEND_URL.",
            "profile": profile,
            "text": text,
        }

    if settings.tts_backend_url:
        return {
            "enabled": True,
            "profile": profile,
            "result": {
                "mode": "backend",
                "message": "External TTS backend is configured. Use /speech/file for audio bytes.",
            },
        }

    if not voice_delivery_enabled():
        return {
            "enabled": False,
            "message": "High-quality TTS backend is not configured yet. Set TTS_BACKEND_URL or explicitly allow the local fallback.",
            "profile": profile,
            "text": text,
        }

    return {
        "enabled": True,
        "profile": profile,
        "result": {
            "mode": "local",
            "message": "Local TTS is enabled. Use /speech/file for audio bytes.",
        },
    }
