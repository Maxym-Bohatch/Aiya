from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import brain
import database as db
import game_agent
import service_control
import translation_engine
import wiki_engine
from config import settings
from tts_engine import synthesize_to_audio_file, tts_capabilities, voice_delivery_enabled

app = FastAPI(title="Aiya Core", version="4.3")


class Query(BaseModel):
    platform: str
    external_id: int
    user_name: str
    text: str


class FeaturePatch(BaseModel):
    tts_enabled: Optional[bool] = None
    ocr_enabled: Optional[bool] = None
    emoji_enabled: Optional[bool] = None
    desktop_subtitles_enabled: Optional[bool] = None
    image_generation_enabled: Optional[bool] = None


class ConsentPatch(BaseModel):
    owner_platform: str
    owner_external_id: int
    grantee_platform: str
    grantee_external_id: int
    can_access_private: bool


class ImageRequest(BaseModel):
    prompt: str


class SpeechRequest(BaseModel):
    text: str


class AliasPatch(BaseModel):
    alias: str
    canonical_name: str


class ScreenObservation(BaseModel):
    platform: str
    external_id: int
    user_name: str
    raw_text: str
    source: str = "desktop"


class ScreenImageObservation(BaseModel):
    platform: str
    external_id: int
    user_name: str
    image_base64: str
    raw_text: str = ""
    source: str = "desktop_image"


class GameSessionRequest(BaseModel):
    platform: str
    external_id: int
    user_name: str
    game_name: str
    profile_name: str = "default"
    goal: str = ""
    screen_summary: str = ""
    capabilities: Optional[dict] = None
    settings: Optional[dict] = None


class GameProfileRequest(BaseModel):
    platform: str
    external_id: int
    user_name: str
    game_name: str
    profile_name: str = "default"
    settings: dict


class GameFeedbackRequest(BaseModel):
    platform: str
    external_id: int
    user_name: str
    game_name: str
    profile_name: str = "default"
    session_id: Optional[int] = None
    verdict: str
    score: int = 0
    note: str = ""
    screen_summary: str = ""
    action_name: str = ""
    action_payload: Optional[dict] = None


class WikiRequest(BaseModel):
    query: str
    language: str = "uk"
    limit: int = 3


class TranslationRequest(BaseModel):
    text: str
    source_language: str = "auto"
    target_language: str = "uk"


class RobotSensorFrame(BaseModel):
    source: str
    sensor_type: str
    payload: dict


class RobotCommandRequest(BaseModel):
    target: str
    command_type: str
    payload: dict = {}


class RobotCommandComplete(BaseModel):
    status: str = "completed"
    result_payload: Optional[dict] = None


class RobotStatePatch(BaseModel):
    profile_name: Optional[str] = None
    body_mode: Optional[str] = None
    notes: Optional[str] = None
    state_payload: Optional[dict] = None


UI_PATH = Path(__file__).with_name("webui.html")


def coding_prompt_addon(text: str) -> str:
    normalized = (text or "").lower()
    keywords = [
        "python",
        "java",
        "код",
        "script",
        "скрипт",
        "fastapi",
        "class",
        "exception",
        "traceback",
        "bug",
        "debug",
        "json",
        "csv",
        "sql",
        "алгоритм",
        "program",
        "програма",
        "програм",
        "функц",
    ]
    if any(keyword in normalized for keyword in keywords):
        return (
            "Це кодовий запит. Дай практичну відповідь: спочатку готовий або майже готовий код, "
            "потім коротко поясни ключові рядки і як це запустити або перевірити. "
            "Особливо якісно підтримуй Python і Java. Не став зайвих уточнень, якщо можна зробити розумне припущення."
        )
    return ""


def coding_language_hint(text: str) -> str:
    normalized = (text or "").lower()
    for candidate in ("python", "java", "javascript", "typescript", "bash", "powershell", "sql"):
        if candidate in normalized:
            return candidate
    if "пайтон" in normalized:
        return "python"
    return ""


def build_coding_answer(user_text: str, system_prompt: str = "") -> str:
    language_hint = coding_language_hint(user_text) or "follow the user's request"
    prompt = (
        (system_prompt.strip() + "\n\n" if system_prompt.strip() else "")
        +
        "You are a careful senior developer.\n"
        "Solve the user's request with one complete code block only.\n"
        "Rules:\n"
        "- Return only the code block.\n"
        "- Make it runnable.\n"
        "- Do not add prose outside the code block.\n"
        "- Keep the solution compact but complete.\n"
        "- Follow the user's requested task exactly.\n"
        "- Do not invent sample data, extra files, or setup unless the user explicitly asked for them.\n"
        "- If the task is to read a JSON file and print a field, open the existing file and print that field.\n"
        f"- Language hint: {language_hint}.\n\n"
        f"User request:\n{user_text}"
    )
    code_only = brain.ask_aiya(
        prompt,
        timeout_seconds=min(settings.performance.llm_timeout_seconds, 120),
        temperature=0.15,
        num_predict=220,
    ).strip()
    if "```" in code_only:
        return f"Ось компактний робочий варіант:\n\n{code_only}"
    return ""


def build_general_answer(user_text: str, system_prompt: str) -> str:
    prompt = (
        f"{system_prompt.strip()}\n\n"
        "Поточне завдання: дай корисну, коротку, фактичну і природну відповідь користувачу.\n"
        "Якщо частина контексту прийшла з wiki-context, використовуй її як довідковий фактологічний матеріал.\n"
        "Якщо релевантних спогадів мало, не вигадуй зайвого.\n\n"
        f"Запит користувача:\n{user_text}"
    )
    answer = brain.ask_aiya(
        prompt,
        timeout_seconds=min(settings.performance.llm_timeout_seconds, 90),
        temperature=0.2,
        num_predict=260,
    ).strip()
    return answer


async def get_aiya_token(x_aiya_token: str = Header(default=None)):
    return x_aiya_token or ""


def background_processing_task(internal_id: int, user_name: str, text: str, level: int):
    try:
        facts_data = brain.extract_facts(user_name, text)
        for fact_obj in facts_data:
            fact_text = fact_obj.get("text") if isinstance(fact_obj, dict) else str(fact_obj)
            fact_level = fact_obj.get("level", level) if isinstance(fact_obj, dict) else level
            if not fact_text:
                continue
            vector = brain.get_embedding(fact_text)
            db.save_fact(internal_id, fact_text, vector, level=fact_level)
        db.refresh_user_profile_summary(internal_id)

        graph_data = brain.extract_entities_and_relations(text)
        if graph_data.get("to_add") or graph_data.get("to_remove"):
            db.update_graph(internal_id, graph_data.get("to_add", []), graph_data.get("to_remove", []))

        history = db.get_recent_logs(internal_id, limit=settings.performance.recent_logs)
        mood_report = brain.update_aiya_mood(user_name, history)
        db.update_user_state(
            internal_id,
            mood_report.get("mood", "stable"),
            mood_report.get("prompt_addon", ""),
        )
    except Exception as exc:
        print(f"Background task error: {exc}")


@app.on_event("startup")
def startup():
    db.ensure_schema()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_mode": settings.llm_mode,
        "llm_provider": settings.llm_provider,
        "ollama_host": settings.ollama_host,
        "llm_base_url": settings.llm_base_url if settings.llm_provider == "openai_compatible" else "",
        "features": {
            "tts": settings.enable_tts,
            "ocr": settings.enable_ocr,
            "image_generation": settings.enable_image_generation,
            "desktop_subtitles": settings.enable_desktop_subtitles,
            "emoji": settings.enable_emoji,
            "screen_context": settings.enable_screen_context,
            "game_mode": settings.enable_game_mode,
            "vision": settings.enable_vision,
            "wiki": settings.enable_wiki,
        },
        "performance": settings.performance.name,
        "hardware_class": settings.hardware_class,
        "chat_model": settings.chat_model,
        "translation_model": settings.translation_model,
        "vision_model": settings.vision_model,
        "tts": tts_capabilities(),
        "service_control": service_control.capabilities(include_remote=False),
        "robot_bridge": {"enabled": True},
    }


@app.get("/", response_class=HTMLResponse)
def aiya_web():
    if not UI_PATH.exists():
        raise HTTPException(status_code=404, detail="UI file is missing")
    return UI_PATH.read_text(encoding="utf-8")


@app.get("/ui", response_class=HTMLResponse)
def aiya_web_alias():
    return aiya_web()


@app.post("/ask")
async def ask_aiya(query: Query, background_tasks: BackgroundTasks, x_token: str = Depends(get_aiya_token)):
    try:
        control_reply = service_control.handle_text_command(query.text)
        if control_reply:
            return {
                "answer": control_reply,
                "user_id": 0,
                "features": {},
                "tts_available": False,
                "image_generation_available": False,
            }

        internal_id = db.get_internal_user(query.platform, query.external_id, query.user_name)
        if internal_id is None:
            raise HTTPException(status_code=500, detail="User mapping failed")

        level = db.get_token_level(internal_id, x_token)
        dispatch = brain.needs_active_search(query.text)
        search_query = dispatch.get("search_query", query.text) if dispatch.get("needs_search") else query.text

        recent_logs = db.get_recent_logs(internal_id, limit=settings.performance.recent_logs)
        query_vec = brain.get_embedding(search_query)
        memories = db.find_smart_memories(
            internal_id,
            query_vec,
            limit=settings.performance.context_memories,
            viewer_user_id=internal_id,
            viewer_level=level,
        )
        screen_context = db.get_recent_screen_context(internal_id, limit=2) if settings.enable_screen_context else ""
        user_summary, user_level = db.get_user_profile(internal_id, query.user_name)
        current_mood, prompt_addon = db.get_user_state(internal_id)
        graph_context = db.find_graph_context(internal_id, search_query, limit=4)
        wiki_context = wiki_engine.get_wiki_context(search_query, language="uk", limit=2)
        combined_memories = list(memories) + list(graph_context) + list(wiki_context)
        coding_addon = coding_prompt_addon(query.text)
        if coding_addon:
            prompt_addon = f"{prompt_addon}\n{coding_addon}".strip()
        if wiki_context:
            prompt_addon = f"{prompt_addon}\nВикористай wiki-context обережно як зовнішню довідку.".strip()
        user_settings = db.get_user_settings(internal_id)
        system_prompt = brain.build_system_prompt(
            user_summary=user_summary,
            current_mood=current_mood,
            prompt_addon=prompt_addon,
            memories=combined_memories,
            recent_logs=recent_logs,
            user_level=user_level,
            screen_context=screen_context,
        )

        if coding_addon:
            answer = build_coding_answer(query.text, system_prompt=system_prompt)
        else:
            answer = build_general_answer(query.text, system_prompt=system_prompt)
        if not answer:
            answer = "Я трохи зависла. Спробуй перефразувати або повторити запит."

        answer = brain.maybe_add_emoji(answer, user_settings.get("emoji_enabled", True))

        db.save_chat_log(internal_id, "user", query.text)
        db.save_chat_log(internal_id, "aiya", answer)
        background_tasks.add_task(background_processing_task, internal_id, query.user_name, query.text, level)

        return {
            "answer": answer,
            "user_id": internal_id,
            "features": user_settings,
            "tts_available": bool(user_settings.get("tts_enabled", False))
            and bool((settings.enable_tts or settings.tts_backend_url) and voice_delivery_enabled()),
            "image_generation_available": settings.enable_image_generation and user_settings.get("image_generation_enabled", False),
            "chat_model": settings.chat_model,
            "llm_provider": settings.llm_provider,
        }
    except HTTPException:
        raise
    except Exception as exc:
        print(f"Critical API error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/users/{platform}/{external_id}/features")
def get_features(platform: str, external_id: int):
    user_id = db.get_internal_user(platform, external_id, platform)
    if user_id is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db.get_user_settings(user_id)


@app.patch("/users/{platform}/{external_id}/features")
def patch_features(platform: str, external_id: int, patch: FeaturePatch):
    user_id = db.get_internal_user(platform, external_id, platform)
    if user_id is None:
        raise HTTPException(status_code=404, detail="User not found")
    updates = patch.model_dump(exclude_none=True) if hasattr(patch, "model_dump") else patch.dict(exclude_none=True)
    return db.update_user_settings(user_id, updates)


@app.post("/consent")
def set_consent(payload: ConsentPatch, x_token: str = Depends(get_aiya_token)):
    owner_id = db.get_internal_user(payload.owner_platform, payload.owner_external_id, payload.owner_platform)
    grantee_id = db.get_internal_user(payload.grantee_platform, payload.grantee_external_id, payload.grantee_platform)
    if owner_id is None or grantee_id is None:
        raise HTTPException(status_code=404, detail="User mapping failed")

    if db.get_token_level(owner_id, x_token) < 10:
        raise HTTPException(status_code=403, detail="Only admin can manage cross-user consent right now")

    db.upsert_consent(owner_id, grantee_id, payload.can_access_private)
    return {"ok": True}


@app.post("/users/{platform}/{external_id}/aliases")
def add_alias(platform: str, external_id: int, payload: AliasPatch):
    user_id = db.get_internal_user(platform, external_id, platform)
    if user_id is None:
        raise HTTPException(status_code=404, detail="User not found")
    db.upsert_alias(user_id, payload.alias, payload.canonical_name)
    return {"ok": True, "alias": payload.alias, "canonical_name": payload.canonical_name}


@app.post("/screen/observe")
def observe_screen(payload: ScreenObservation):
    if not settings.enable_screen_context:
        raise HTTPException(status_code=503, detail="Screen context is disabled")
    user_id = db.get_internal_user(payload.platform, payload.external_id, payload.user_name)
    if user_id is None:
        raise HTTPException(status_code=404, detail="User not found")
    result = game_agent.record_screen_observation(user_id, payload.raw_text, source=payload.source)
    return {"ok": True, **result}


@app.post("/screen/analyze-image")
def analyze_screen_image(payload: ScreenImageObservation):
    if not settings.enable_screen_context:
        raise HTTPException(status_code=503, detail="Screen context is disabled")
    user_id = db.get_internal_user(payload.platform, payload.external_id, payload.user_name)
    if user_id is None:
        raise HTTPException(status_code=404, detail="User not found")
    summary = game_agent.analyze_screen_image(payload.image_base64, payload.raw_text)
    db.save_screen_observation(user_id, raw_text=payload.raw_text, summary=summary, source=payload.source)
    return {"ok": True, "summary": summary}


@app.post("/game/plan")
def game_plan(payload: GameSessionRequest):
    if not settings.enable_game_mode:
        raise HTTPException(status_code=503, detail="Game mode is disabled")
    user_id = db.get_internal_user(payload.platform, payload.external_id, payload.user_name)
    if user_id is None:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.settings:
        db.upsert_game_profile(user_id, payload.game_name, payload.profile_name, payload.settings)
    profile = db.get_game_profile(user_id, payload.game_name, payload.profile_name)
    session_id = db.create_or_get_game_session(
        user_id,
        payload.game_name,
        payload.goal,
        profile_name=payload.profile_name,
        metadata={"capabilities": payload.capabilities or {}, "profile": profile},
    )
    db.log_game_event(session_id, event_type="screen", screen_summary=payload.screen_summary, outcome="observed")
    recent_events = db.get_recent_game_events(session_id, limit=8)
    feedback_rows = db.get_recent_game_feedback(session_id, limit=6)
    plan = game_agent.build_game_action_plan(
        user_id,
        payload.game_name,
        payload.goal,
        payload.screen_summary,
        recent_events,
        payload.capabilities,
        profile_name=payload.profile_name,
        profile=profile,
        session_feedback=feedback_rows,
    )
    for action in plan.get("actions", []):
        db.log_game_event(
            session_id,
            event_type="planned_action",
            screen_summary=payload.screen_summary,
            action_name=action.get("control", ""),
            action_payload=action,
            outcome=plan.get("reasoning", ""),
        )
    return {"session_id": session_id, "profile": profile, "plan": plan}


@app.get("/game/profile/{platform}/{external_id}")
def get_game_profile(platform: str, external_id: int, game_name: str, profile_name: str = "default", user_name: str = "desktop"):
    user_id = db.get_internal_user(platform, external_id, user_name)
    if user_id is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db.get_game_profile(user_id, game_name, profile_name)


@app.post("/game/profile")
def save_game_profile(payload: GameProfileRequest):
    user_id = db.get_internal_user(payload.platform, payload.external_id, payload.user_name)
    if user_id is None:
        raise HTTPException(status_code=404, detail="User not found")
    profile = db.upsert_game_profile(user_id, payload.game_name, payload.profile_name, payload.settings)
    return {"ok": True, "profile": profile}


@app.post("/game/feedback")
def game_feedback(payload: GameFeedbackRequest):
    user_id = db.get_internal_user(payload.platform, payload.external_id, payload.user_name)
    if user_id is None:
        raise HTTPException(status_code=404, detail="User not found")
    session_id = payload.session_id or db.create_or_get_game_session(
        user_id,
        payload.game_name,
        goal="",
        profile_name=payload.profile_name,
    )
    feedback_id = db.record_game_feedback(
        session_id,
        verdict=payload.verdict,
        score=payload.score,
        note=payload.note,
        screen_summary=payload.screen_summary,
        action_name=payload.action_name,
        action_payload=payload.action_payload,
    )
    db.log_game_event(
        session_id,
        event_type="feedback",
        screen_summary=payload.screen_summary,
        action_name=payload.action_name,
        action_payload=payload.action_payload,
        outcome=f"{payload.verdict}:{payload.note}".strip(":"),
    )
    note_id = game_agent.reinforce_from_feedback(
        user_id,
        payload.game_name,
        payload.profile_name,
        payload.screen_summary,
        payload.verdict,
        payload.note,
        payload.action_name,
    )
    if payload.verdict.lower() == "goal":
        db.update_game_session_status(session_id, "completed", metadata={"last_verdict": payload.verdict})
    elif payload.verdict.lower() == "stuck":
        db.update_game_session_status(session_id, "running", metadata={"last_verdict": payload.verdict})
    snapshot = db.get_game_session_snapshot(session_id)
    return {"ok": True, "feedback_id": feedback_id, "learning_note_id": note_id, "session": snapshot}


@app.get("/game/session/{session_id}")
def game_session(session_id: int):
    snapshot = db.get_game_session_snapshot(session_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Game session not found")
    return snapshot


@app.post("/image/generate")
def image_generate(payload: ImageRequest):
    result = brain.generate_image(payload.prompt)
    if result.get("enabled") is False:
        raise HTTPException(status_code=503, detail=result["message"])
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@app.post("/image/file")
def image_file(payload: ImageRequest):
    result = brain.generate_image(payload.prompt)
    if result.get("enabled") is False:
        raise HTTPException(status_code=503, detail=result["message"])
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    result_data = result.get("result", {})
    if result_data.get("mode") == "local" and result_data.get("path"):
        return FileResponse(result_data["path"], media_type="image/png", filename="aiya_image.png")
    raise HTTPException(status_code=501, detail="Remote image backend does not expose a local file")


@app.post("/speech/synthesize")
def synthesize(payload: SpeechRequest):
    result = brain.synthesize_speech(payload.text)
    if result.get("enabled") is False:
        raise HTTPException(status_code=503, detail=result["message"])
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    return result


@app.post("/speech/file")
def synthesize_file(payload: SpeechRequest):
    if not settings.enable_tts and not settings.tts_backend_url:
        raise HTTPException(status_code=503, detail="TTS is disabled")
    try:
        audio_path, media_type, filename = synthesize_to_audio_file(payload.text)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return FileResponse(audio_path, media_type=media_type, filename=filename)


@app.get("/speech/capabilities")
def speech_capabilities():
    return tts_capabilities()


@app.get("/game/capabilities")
def game_capabilities():
    return {
        "enabled": settings.enable_game_mode,
        "note": "Execution capabilities are provided by the desktop companion host backend.",
    }


@app.get("/control/capabilities")
def control_capabilities():
    return service_control.capabilities()


@app.get("/wiki/capabilities")
def wiki_capabilities():
    return wiki_engine.wiki_capabilities()


@app.post("/wiki/search")
def wiki_search(payload: WikiRequest):
    result = wiki_engine.search_wiki(payload.query, language=payload.language, limit=payload.limit)
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("message", "Wiki search failed"))
    return result


@app.get("/robot/capabilities")
def robot_capabilities():
    return {
        "enabled": True,
        "control_modes": ["gamepad", "keyboard", "robot_api"],
        "sensor_ingest": ["/robot/sensors", "/screen/observe", "/screen/analyze-image"],
        "command_queue": ["/robot/commands", "/robot/commands/next", "/robot/commands/{id}/complete"],
        "state_endpoints": ["/robot/state"],
        "note": "Use this bridge to attach future camera, sensor, telemetry, and actuator modules without hardcoding specific hardware into Aiya core.",
    }


@app.get("/robot/state")
def get_robot_state():
    return db.get_robot_state()


@app.patch("/robot/state")
def patch_robot_state(payload: RobotStatePatch):
    return db.update_robot_state(
        profile_name=payload.profile_name,
        body_mode=payload.body_mode,
        notes=payload.notes,
        state_payload=payload.state_payload,
    )


@app.post("/robot/sensors")
def post_robot_sensor(payload: RobotSensorFrame):
    saved = db.save_robot_sensor_frame(payload.source, payload.sensor_type, payload.payload)
    return {"ok": True, **saved}


@app.get("/robot/sensors/recent")
def recent_robot_sensors(limit: int = 20):
    return {"items": db.get_recent_robot_sensor_frames(limit=max(1, min(limit, 100)))}


@app.post("/robot/commands")
def queue_robot_command(payload: RobotCommandRequest):
    saved = db.queue_robot_command(payload.target, payload.command_type, payload.payload)
    return {"ok": True, **saved}


@app.get("/robot/commands/next")
def next_robot_command(target: str):
    command = db.claim_next_robot_command(target)
    return {"ok": bool(command), "command": command}


@app.post("/robot/commands/{command_id}/complete")
def complete_robot_command(command_id: int, payload: RobotCommandComplete):
    return db.complete_robot_command(command_id, status=payload.status, result_payload=payload.result_payload)


@app.post("/translate")
def translate(payload: TranslationRequest):
    result = translation_engine.translate_text(
        payload.text,
        source_lang=payload.source_language,
        target_lang=payload.target_language,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("message", "Translation failed"))
    return result


@app.post("/control/services/{service_name}/start")
def start_service(service_name: str):
    result = service_control.start_service(service_name)
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("message", "Service start failed"))
    return result


@app.post("/control/services/{service_name}/restart")
def restart_service(service_name: str):
    result = service_control.remote_start_service(service_name)
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("message", "Service restart failed"))
    return result


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
