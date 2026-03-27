import os
import platform
from dataclasses import dataclass

from dotenv import load_dotenv


def _load_environment():
    override = (os.getenv("AIYA_ENV_FILE") or "").strip()
    if override:
        load_dotenv(dotenv_path=override, override=True)
        return

    if os.path.exists(".env"):
        load_dotenv(".env", override=True)
        return

    if os.path.exists(".env.client"):
        load_dotenv(".env.client", override=True)


_load_environment()


def _as_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_or_default(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    return raw if raw else default


def _env_token_list(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return ()
    tokens = []
    for part in raw.replace(";", ",").split(","):
        token = part.strip()
        if token and token not in tokens:
            tokens.append(token)
    return tuple(tokens)


@dataclass(frozen=True)
class PerformanceProfile:
    name: str
    chat_model: str
    embed_model: str
    vision_model: str
    context_memories: int
    recent_logs: int
    ocr_interval_seconds: int
    screen_summary_interval_seconds: int
    llm_timeout_seconds: int
    desktop_fps: int


PROFILES = {
    "low": PerformanceProfile(
        name="low",
        chat_model=os.getenv("OLLAMA_CHAT_MODEL_LOW", "qwen2.5:1.5b"),
        embed_model=os.getenv("OLLAMA_EMBED_MODEL_LOW", "nomic-embed-text"),
        vision_model=os.getenv("OLLAMA_VISION_MODEL_LOW", "llava:7b"),
        context_memories=4,
        recent_logs=4,
        ocr_interval_seconds=8,
        screen_summary_interval_seconds=12,
        llm_timeout_seconds=120,
        desktop_fps=12,
    ),
    "balanced": PerformanceProfile(
        name="balanced",
        chat_model=os.getenv("OLLAMA_CHAT_MODEL_BALANCED", "qwen2.5:3b"),
        embed_model=os.getenv("OLLAMA_EMBED_MODEL_BALANCED", "nomic-embed-text"),
        vision_model=os.getenv("OLLAMA_VISION_MODEL_BALANCED", "llava:7b"),
        context_memories=8,
        recent_logs=7,
        ocr_interval_seconds=4,
        screen_summary_interval_seconds=8,
        llm_timeout_seconds=180,
        desktop_fps=20,
    ),
    "high": PerformanceProfile(
        name="high",
        chat_model=os.getenv("OLLAMA_CHAT_MODEL_HIGH", "qwen2.5:7b"),
        embed_model=os.getenv("OLLAMA_EMBED_MODEL_HIGH", "nomic-embed-text"),
        vision_model=os.getenv("OLLAMA_VISION_MODEL_HIGH", "llava:13b"),
        context_memories=12,
        recent_logs=10,
        ocr_interval_seconds=2,
        screen_summary_interval_seconds=5,
        llm_timeout_seconds=240,
        desktop_fps=30,
    ),
}


def detect_hardware_class() -> str:
    override = os.getenv("AIYA_HARDWARE_CLASS", "").strip().lower()
    if override in {"cpu", "amd", "nvidia", "intel"}:
        return override

    machine = platform.machine().lower()
    processor = platform.processor().lower()
    combined = f"{machine} {processor}"
    if "amd" in combined or "ryzen" in combined or "radeon" in combined:
        return "amd"
    if "nvidia" in combined or "geforce" in combined or "rtx" in combined or "gtx" in combined:
        return "nvidia"
    if "intel" in combined:
        return "intel"
    return "cpu"


def select_profile_name() -> str:
    requested = os.getenv("AIYA_PERFORMANCE_PROFILE", "auto").strip().lower()
    if requested in PROFILES:
        return requested
    hardware = detect_hardware_class()
    if hardware == "cpu":
        return "balanced"
    if hardware in {"intel", "amd"}:
        return "balanced"
    return "high"


@dataclass(frozen=True)
class AppConfig:
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"postgresql://maxim:{os.getenv('DB_PASSWORD', '')}@localhost:5433/aiya_memory",
    )
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    api_url: str = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
    remote_web_url: str = (os.getenv("REMOTE_WEB_URL") or "http://localhost:3000").rstrip("/")
    remote_open_webui_url: str = (os.getenv("REMOTE_OPEN_WEBUI_URL") or "http://localhost:3001").rstrip("/")
    telegram_token: str = (os.getenv("TELEGRAM_TOKEN") or "").strip()
    admin_token: str = (os.getenv("AIYA_ADMIN_TOKEN") or "").strip()
    extra_admin_tokens: tuple[str, ...] = _env_token_list("AIYA_EXTRA_ADMIN_TOKENS")
    image_backend_url: str = (os.getenv("IMAGE_BACKEND_URL") or "").rstrip("/")
    tts_backend_url: str = (os.getenv("TTS_BACKEND_URL") or "").rstrip("/")
    translation_backend_url: str = (os.getenv("TRANSLATION_BACKEND_URL") or "").rstrip("/")
    host_control_url: str = (os.getenv("HOST_CONTROL_URL") or "http://host.docker.internal:8765").rstrip("/")
    host_control_token: str = (os.getenv("HOST_CONTROL_TOKEN") or os.getenv("AIYA_ADMIN_TOKEN") or "").strip()
    client_mode: str = (os.getenv("AIYA_CLIENT_MODE") or "desktop").strip().lower()
    client_user_name: str = (os.getenv("AIYA_CLIENT_USER_NAME") or "DesktopUser").strip()
    client_external_id: int = int((os.getenv("AIYA_CLIENT_EXTERNAL_ID") or "900001").strip())
    client_platform: str = (os.getenv("AIYA_CLIENT_PLATFORM") or "desktop").strip()
    tesseract_cmd: str = (os.getenv("AIYA_TESSERACT_CMD") or "").strip()
    ocr_languages: str = (os.getenv("AIYA_OCR_LANGS") or "ukr+eng").strip()
    client_translation_source_lang: str = (os.getenv("AIYA_TRANSLATION_SOURCE_LANG") or "auto").strip()
    client_translation_target_lang: str = (os.getenv("AIYA_TRANSLATION_TARGET_LANG") or "uk").strip()
    character_asset: str = (os.getenv("AIYA_CHARACTER_ASSET") or "").strip()
    character_dock: str = (os.getenv("AIYA_CHARACTER_DOCK") or "right").strip().lower()
    character_scale: float = float((os.getenv("AIYA_CHARACTER_SCALE") or "1.0").strip())
    subtitle_overlay_enabled: bool = _as_bool("AIYA_SUBTITLE_OVERLAY", True)
    character_overlay_enabled: bool = _as_bool("AIYA_CHARACTER_OVERLAY", True)
    subtitle_color: str = (os.getenv("AIYA_SUBTITLE_COLOR") or "#a8ff9c").strip()
    enable_tts: bool = _as_bool("ENABLE_TTS", True)
    enable_ocr: bool = _as_bool("ENABLE_OCR", False)
    enable_image_generation: bool = _as_bool("ENABLE_IMAGE_GENERATION", False)
    enable_desktop_subtitles: bool = _as_bool("ENABLE_DESKTOP_SUBTITLES", True)
    enable_emoji: bool = _as_bool("ENABLE_EMOJI", True)
    enable_screen_context: bool = _as_bool("ENABLE_SCREEN_CONTEXT", True)
    enable_game_mode: bool = _as_bool("ENABLE_GAME_MODE", True)
    enable_vision: bool = _as_bool("ENABLE_VISION", True)
    enable_wiki: bool = _as_bool("ENABLE_WIKI", True)
    tts_provider: str = (os.getenv("AIYA_TTS_PROVIDER") or "edge").strip().lower()
    tts_voice: str = (os.getenv("TTS_VOICE") or "uk-UA-PolinaNeural").strip()
    tts_rate: str = (os.getenv("AIYA_TTS_RATE") or "+0%").strip()
    tts_pitch: str = (os.getenv("AIYA_TTS_PITCH") or "+0Hz").strip()
    translation_model_name: str = (os.getenv("AIYA_TRANSLATION_MODEL") or "").strip()
    hardware_class: str = detect_hardware_class()
    performance_profile_name: str = select_profile_name()

    @property
    def performance(self) -> PerformanceProfile:
        return PROFILES[self.performance_profile_name]

    @property
    def ollama_chat_model(self) -> str:
        return _env_or_default("OLLAMA_CHAT_MODEL", self.performance.chat_model)

    @property
    def ollama_embed_model(self) -> str:
        return _env_or_default("OLLAMA_EMBED_MODEL", self.performance.embed_model)

    @property
    def ollama_vision_model(self) -> str:
        return _env_or_default("OLLAMA_VISION_MODEL", self.performance.vision_model)

    @property
    def translation_model(self) -> str:
        return self.translation_model_name or self.ollama_chat_model


settings = AppConfig()
