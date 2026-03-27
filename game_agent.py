import json

import brain
import database as db
import vision_engine

SUPPORTED_ACTIONS = {"press", "gamepad_button", "move_left_stick"}


def summarize_screen(raw_text: str) -> str:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return ""
    prompt = f"""
Ти модуль screen-vision Айї.
Стисни OCR-текст до короткого опису того, що бачить користувач на екрані.
Поверни 1-3 короткі речення українською.

OCR:
{raw_text}
"""
    summary = brain.ask_aiya(prompt).strip()
    return summary or raw_text[:300]


def analyze_screen_image(image_b64: str, raw_text: str = "") -> str:
    visual_summary = vision_engine.analyze_image(image_b64)
    if visual_summary:
        if raw_text:
            return f"{visual_summary}\nOCR: {raw_text[:300]}"
        return visual_summary
    return summarize_screen(raw_text)


def _filter_actions(actions, capabilities: dict) -> list[dict]:
    filtered = []
    allow_keyboard = bool(capabilities.get("keyboard", False))
    allow_gamepad = bool(capabilities.get("gamepad", False))
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        if action_type not in SUPPORTED_ACTIONS:
            continue
        if action_type == "press" and not allow_keyboard:
            continue
        if action_type in {"gamepad_button", "move_left_stick"} and not allow_gamepad:
            continue
        filtered.append(action)
    return filtered[:4]


def build_game_action_plan(game_name: str, goal: str, screen_summary: str, recent_events, capabilities=None) -> dict:
    capabilities = capabilities or {"keyboard": True, "gamepad": False, "mode": "keyboard"}
    recent_text = "\n".join(
        [
            f"- type={event_type}; screen={screen}; action={action}; outcome={outcome}"
            for event_type, screen, action, outcome in recent_events
        ]
    ) or "- Поки що без попередніх подій."
    prompt = f"""
Ти ігровий агент Айї.
Гра: {game_name}
Ціль: {goal}
Поточна сцена: {screen_summary}
Доступні способи керування: {capabilities}
Нещодавні події:
{recent_text}

Поверни лише JSON:
{{
  "reasoning": "коротко і по суті",
  "actions": [
    {{"type": "press", "control": "w", "duration_ms": 250}},
    {{"type": "press", "control": "space", "duration_ms": 120}},
    {{"type": "gamepad_button", "control": "a", "duration_ms": 120}},
    {{"type": "move_left_stick", "x": 0.0, "y": 1.0, "duration_ms": 250}}
  ]
}}

Правила:
- Використовуй лише ті типи дій, які підтримують доступні способи керування.
- Не пропонуй більше 4 дій за один цикл.
- Якщо сцена не дає зрозумілого наступного кроку, поверни actions: [] і коротко поясни чому.
"""
    raw = brain.ask_aiya(prompt, format="json")
    try:
        data = json.loads(brain.clean_json_response(raw))
        if not isinstance(data, dict):
            return {"reasoning": "invalid response", "actions": []}
        filtered_actions = _filter_actions(data.get("actions", []), capabilities)
        return {
            "reasoning": (data.get("reasoning") or "no reasoning").strip(),
            "actions": filtered_actions,
        }
    except Exception:
        return {"reasoning": "fallback", "actions": []}


def record_screen_observation(user_id: int, raw_text: str, source="desktop") -> dict:
    summary = summarize_screen(raw_text)
    db.save_screen_observation(user_id, raw_text=raw_text, summary=summary, source=source)
    return {"summary": summary}
