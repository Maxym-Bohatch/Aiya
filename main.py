from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel
import uvicorn

import brain
import database as db
import game_agent
import service_control
import translation_engine
import wiki_engine
from config import settings
from tts_engine import synthesize_to_audio_file, tts_capabilities, voice_delivery_enabled

app = FastAPI(title="Aiya Core", version="4.0")


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
    goal: str = ""
    screen_summary: str = ""
    capabilities: Optional[dict] = None


class WikiRequest(BaseModel):
    query: str
    language: str = "uk"
    limit: int = 3


class TranslationRequest(BaseModel):
    text: str
    source_language: str = "auto"
    target_language: str = "uk"


UI_PATH = Path(__file__).with_name("webui.html")


def coding_prompt_addon(text: str) -> str:
    normalized = (text or "").lower()
    keywords = [
        "python", "java", "код", "script", "скрипт", "fastapi", "class",
        "exception", "traceback", "bug", "debug", "json", "csv",
        "sql", "алгоритм", "program", "програма", "програм", "функц",
    ]
    if any(keyword in normalized for keyword in keywords):
        return (
            "Це кодовий запит. Дай практичну відповідь: спочатку готовий або майже готовий "
            "код, потім коротко поясни ключові рядки і як це запустити або перевірити. "
            "Особливо якісно підтримуй Python і Java. Не став зайвих зустрічних питань, "
            "якщо можна зробити розумне припущення."
        )
    return ""


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
            vec = brain.get_embedding(fact_text)
            db.save_fact(internal_id, fact_text, vec, level=fact_level)

        graph_data = brain.extract_entities_and_relations(text)
        if graph_data.get("to_add") or graph_data.get("to_remove"):
            db.update_graph(
                internal_id,
                graph_data.get("to_add", []),
                graph_data.get("to_remove", []),
            )

        history = db.get_recent_logs(internal_id, limit=settings.performance.recent_logs)
        mood_report = brain.update_aiya_mood(user_name, history)
        db.update_user_state(
            internal_id,
            mood_report.get("mood", "stable"),
            mood_report.get("prompt_addon", ""),
        )
    except Exception as e:
        print(f"Background task error: {e}")


@app.on_event("startup")
def startup():
    db.ensure_schema()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "ollama_host": settings.ollama_host,
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
        "service_control": service_control.capabilities(include_remote=False),
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
        coding_addon = coding_prompt_addon(query.text)
        if coding_addon:
            prompt_addon = f"{prompt_addon}\n{coding_addon}".strip()
        user_settings = db.get_user_settings(internal_id)

        system_prompt = brain.build_system_prompt(
            user_summary=user_summary,
            current_mood=current_mood,
            prompt_addon=prompt_addon,
            memories=memories,
            recent_logs=recent_logs,
            user_level=user_level,
            screen_context=screen_context,
        )
        full_prompt = f'{system_prompt}\nЗАПИТ КОРИСТУВАЧА: "{query.text}"'
        answer = brain.ask_aiya(full_prompt).strip()
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
            "tts_available": bool(user_settings.get("tts_enabled", False)) and bool(
                (settings.enable_tts or settings.tts_backend_url) and voice_delivery_enabled()
            ),
            "image_generation_available": settings.enable_image_generation and user_settings.get("image_generation_enabled", False),
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Critical API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    if hasattr(patch, "model_dump"):
        updates = patch.model_dump(exclude_none=True)
    else:
        updates = patch.dict(exclude_none=True)
    return db.update_user_settings(user_id, updates)


@app.post("/consent")
def set_consent(payload: ConsentPatch, x_token: str = Depends(get_aiya_token)):
    owner_id = db.get_internal_user(payload.owner_platform, payload.owner_external_id, payload.owner_platform)
    grantee_id = db.get_internal_user(payload.grantee_platform, payload.grantee_external_id, payload.grantee_platform)
    if owner_id is None or grantee_id is None:
        raise HTTPException(status_code=404, detail="User mapping failed")

    is_admin = db.get_token_level(owner_id, x_token) >= 10
    if not is_admin:
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

    session_id = db.create_or_get_game_session(user_id, payload.game_name, payload.goal)
    db.log_game_event(
        session_id,
        event_type="screen",
        screen_summary=payload.screen_summary,
        outcome="observed",
    )
    recent_events = db.get_recent_game_events(session_id, limit=8)
    plan = game_agent.build_game_action_plan(
        payload.game_name,
        payload.goal,
        payload.screen_summary,
        recent_events,
        payload.capabilities,
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
    return {"session_id": session_id, "plan": plan}


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
        return FileResponse(
            result_data["path"],
            media_type="image/png",
            filename="aiya_image.png",
        )
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
    return FileResponse(
        audio_path,
        media_type=media_type,
        filename=filename,
    )


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
