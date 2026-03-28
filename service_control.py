import shutil
import subprocess
from pathlib import Path

import requests

from config import settings

PROJECT_DIR = Path(__file__).resolve().parent

SERVICE_COMMANDS = {
    "telegram": ["up", "-d", "api", "tg_bot"],
    "tg_bot": ["up", "-d", "api", "tg_bot"],
    "api": ["up", "-d", "api"],
    "web": ["up", "-d", "api", "webui"],
}


def _supported_services() -> list[str]:
    services = sorted(set(SERVICE_COMMANDS))
    if (getattr(settings, "llm_provider", "") or "").lower() == "openai_compatible":
        return [name for name in services if name != "web"]
    return services


def _compose_base() -> list[str]:
    if settings.llm_mode == "external_ollama":
        return ["docker", "compose", "-f", "docker-compose.external-ollama.yml"]
    if settings.llm_mode == "external_api":
        return ["docker", "compose", "-f", "docker-compose.external-api.yml"]
    return ["docker", "compose", "-f", "docker-compose.yml"]


def capabilities(include_remote: bool = True) -> dict:
    data = {
        "docker_cli": shutil.which("docker") is not None,
        "supported_services": _supported_services(),
        "mode": "best-effort local control",
        "host_control_url": settings.host_control_url,
    }
    if include_remote:
        data["host_bridge"] = host_capabilities()
    return data


def start_service(service_name: str) -> dict:
    normalized = (service_name or "").strip().lower()
    if normalized == "web" and (getattr(settings, "llm_provider", "") or "").lower() == "openai_compatible":
        return {"ok": False, "message": "WebUI service is unavailable in external API mode."}
    command_args = SERVICE_COMMANDS.get(normalized)
    if not command_args:
        return {
            "ok": False,
            "message": f"Unknown service '{service_name}'. Supported: {', '.join(_supported_services())}.",
        }
    command = [*_compose_base(), *command_args]

    remote = remote_start_service(normalized)
    if remote.get("ok"):
        return remote

    if shutil.which("docker") is None:
        return {
            "ok": False,
            "message": remote.get(
                "message",
                "Docker CLI is unavailable here, so I cannot start local containers from this runtime.",
            ),
        }

    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )
        output = (completed.stdout or completed.stderr or "").strip()
        return {
            "ok": True,
            "service": normalized,
            "message": output or f"Requested start for {normalized}.",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"Starting {normalized} timed out."}
    except Exception as exc:
        return {"ok": False, "message": f"Failed to start {normalized}: {exc}"}


def handle_text_command(text: str) -> str:
    normalized = " ".join((text or "").strip().lower().split())
    if not normalized:
        return ""

    telegram_phrases = [
        "підніми телеграм",
        "запусти телеграм",
        "увімкни телеграм",
        "start telegram",
        "start tg",
        "/start telegram",
        "/system start telegram",
    ]
    api_phrases = [
        "підніми api",
        "запусти api",
        "start api",
        "/system start api",
    ]
    web_phrases = [
        "підніми web",
        "запусти web",
        "підніми веб",
        "запусти веб",
        "start web",
        "/system start web",
    ]

    if any(phrase in normalized for phrase in telegram_phrases):
        return start_service("telegram")["message"]
    if any(phrase in normalized for phrase in api_phrases):
        return start_service("api")["message"]
    if any(phrase in normalized for phrase in web_phrases):
        return start_service("web")["message"]
    return ""


def host_capabilities() -> dict:
    return _host_request("GET", "/capabilities")


def remote_start_service(service_name: str) -> dict:
    return _host_request("POST", f"/services/{service_name}/start")


def _host_request(method: str, path: str) -> dict:
    if not settings.host_control_url:
        return {"ok": False, "message": "HOST_CONTROL_URL is not configured."}

    headers = {}
    if settings.host_control_token:
        headers["X-Aiya-Host-Token"] = settings.host_control_token

    try:
        response = requests.request(method, f"{settings.host_control_url}{path}", headers=headers, timeout=15)
        data = response.json()
        if isinstance(data, dict):
            data.setdefault("ok", response.ok)
            return data
        return {"ok": response.ok, "message": str(data)}
    except Exception as exc:
        return {"ok": False, "message": f"Host control unavailable: {exc}"}
