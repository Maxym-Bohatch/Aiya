import json

import brain
import database as db
import vision_engine


def summarize_screen(raw_text: str) -> str:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        return ""
    prompt = f"""
You are Aiya's screen-vision module.
Compress the OCR text into a short, useful scene summary.
Return 1-3 short sentences in Ukrainian and keep game-relevant objects, threats, prompts, and UI hints.

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


def _clip_text(text: str, limit: int) -> str:
    return (text or "").strip()[:limit]


def _filter_actions(actions: list[dict], capabilities: dict, max_actions: int = 4) -> list[dict]:
    if not isinstance(actions, list):
        return []
    filtered = []
    keyboard_allowed = bool(capabilities.get("keyboard", True))
    gamepad_allowed = bool(capabilities.get("gamepad", False))
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = action.get("type")
        if action_type == "press" and keyboard_allowed:
            filtered.append(action)
        elif action_type in {"gamepad_button", "move_left_stick"} and gamepad_allowed:
            filtered.append(action)
        if len(filtered) >= max_actions:
            break
    return filtered


def _summarize_learning_notes(notes) -> str:
    lines = []
    for cue, lesson, confidence, reinforced, feedback, _updated_at in notes or []:
        lines.append(
            f"- cue={_clip_text(cue, 90)} | lesson={_clip_text(lesson, 150)} | "
            f"confidence={float(confidence or 0):.2f} | reinforced={int(reinforced or 0)} | feedback={_clip_text(feedback, 80)}"
        )
    return "\n".join(lines) or "- no stored lessons yet"


def _summarize_recent_feedback(feedback_rows) -> str:
    lines = []
    for verdict, score, note, screen_summary, action_name, action_payload, _created_at in feedback_rows or []:
        payload_note = ""
        if isinstance(action_payload, dict) and action_payload.get("control"):
            payload_note = f" payload_control={action_payload.get('control')}"
        lines.append(
            f"- verdict={verdict}; score={score}; action={action_name or '-'}{payload_note}; "
            f"note={_clip_text(note, 100)}; screen={_clip_text(screen_summary, 100)}"
        )
    return "\n".join(lines) or "- no feedback yet"


def _detect_loop_pressure(recent_events) -> str:
    recent_controls = [str(action or "").strip().lower() for _event_type, _screen, action, _outcome in recent_events or [] if action]
    if len(recent_controls) < 3:
        return "normal"
    last_three = recent_controls[-3:]
    if len(set(last_three)) == 1:
        return f"looping on {last_three[-1]}"
    return "normal"


def build_game_action_plan(
    user_id: int,
    game_name: str,
    goal: str,
    screen_summary: str,
    recent_events,
    capabilities=None,
    profile_name: str = "default",
    profile: dict | None = None,
    session_feedback=None,
) -> dict:
    capabilities = capabilities or {"keyboard": True, "gamepad": False, "mode": "keyboard"}
    profile = profile or db.get_game_profile(user_id, game_name, profile_name)
    learning_notes = db.get_game_learning_notes(user_id, game_name, profile_name, limit=6) if profile.get("learning_enabled", True) else []
    feedback_rows = session_feedback or []
    recent_text = "\n".join(
        f"- type={event_type}; screen={screen}; action={action}; outcome={outcome}"
        for event_type, screen, action, outcome in recent_events
    ) or "- no recent events"
    learning_text = _summarize_learning_notes(learning_notes)
    feedback_text = _summarize_recent_feedback(feedback_rows)
    loop_pressure = _detect_loop_pressure(recent_events)
    max_actions = max(0, min(int(profile.get("max_actions_per_step", 2) or 2), 4))
    cooldown_ms = max(100, int(profile.get("action_cooldown_ms", 900) or 900))

    prompt = f"""
You are Aiya's tactical game planner.
Game: {game_name}
Profile: {profile_name}
Goal: {goal}
Current scene: {screen_summary}
Available control capabilities: {capabilities}
Profile settings: {json.dumps(profile, ensure_ascii=False)}
Loop pressure: {loop_pressure}

Recent events:
{recent_text}

Recent feedback:
{feedback_text}

Stored learning:
{learning_text}

Return JSON only:
{{
  "reasoning": "short tactical summary",
  "confidence": 0.0,
  "learning_focus": "what to verify next",
  "actions": [
    {{"type": "press", "control": "w", "duration_ms": 250}},
    {{"type": "press", "control": "space", "duration_ms": 120}},
    {{"type": "gamepad_button", "control": "a", "duration_ms": 120}},
    {{"type": "move_left_stick", "x": 0.0, "y": 1.0, "duration_ms": 250}}
  ]
}}

Rules:
- Prefer safe, reversible scouting actions when confidence is low.
- Avoid repeating the same stuck action if recent feedback says it failed or stalled.
- Never exceed {max_actions} actions.
- Use duration_ms close to {cooldown_ms} or lower for cautious movement.
- If the best move is to wait, inspect, or keep observing, return actions: [].
- Use only action types allowed by the control capabilities.
"""
    raw = brain.ask_aiya(
        prompt,
        format="json",
        timeout_seconds=min(brain.settings.performance.llm_timeout_seconds, 45),
        num_predict=180,
    )
    try:
        data = json.loads(brain.clean_json_response(raw))
        if not isinstance(data, dict):
            return {"reasoning": "invalid response", "confidence": 0.0, "learning_focus": "", "actions": [], "profile_name": profile_name}
        data["actions"] = _filter_actions(data.get("actions", []), capabilities, max_actions=max_actions)
        data["reasoning"] = (data.get("reasoning") or "").strip() or "Hold position and gather more signal."
        data["learning_focus"] = (data.get("learning_focus") or "").strip()
        try:
            data["confidence"] = max(0.0, min(1.0, float(data.get("confidence", 0.35))))
        except Exception:
            data["confidence"] = 0.35
        data["profile_name"] = profile_name
        return data
    except Exception:
        return {"reasoning": "fallback", "confidence": 0.0, "learning_focus": "", "actions": [], "profile_name": profile_name}


def record_screen_observation(user_id: int, raw_text: str, source="desktop") -> dict:
    summary = summarize_screen(raw_text)
    db.save_screen_observation(user_id, raw_text=raw_text, summary=summary, source=source)
    return {"summary": summary}


def reinforce_from_feedback(user_id: int, game_name: str, profile_name: str, screen_summary: str, verdict: str, note: str, action_name: str = ""):
    verdict = (verdict or "").strip().lower()
    if verdict not in {"good", "bad", "stuck", "progressed", "goal"}:
        return None
    cue = _clip_text(screen_summary, 140) or f"action:{action_name or 'unknown'}"
    if verdict in {"good", "progressed", "goal"}:
        lesson = note.strip() or f"When you see '{cue}', repeating or building on '{action_name or 'the last move'}' can help."
        confidence = 0.8 if verdict == "goal" else 0.7
    else:
        lesson = note.strip() or f"When you see '{cue}', avoid repeating '{action_name or 'the same move'}' without new evidence."
        confidence = 0.35
    return db.save_game_learning_note(user_id, game_name, profile_name, cue, lesson, confidence=confidence, feedback=verdict)
