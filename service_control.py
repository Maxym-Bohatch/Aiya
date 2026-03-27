import shutil
import subprocess
from pathlib import Path

import requests

from config import settings

PROJECT_DIR = Path(__file__).resolve().parent

SERVICE_COMMANDS = {
    "telegram": ["docker", "compose", "up", "-d", "api", "tg_bot"],
    "tg_bot": ["docker", "compose", "up", "-d", "api", "tg_bot"],
    "api": ["docker", "compose", "up", "-d", "api"],
}


def capabilities(include_remote: bool = True) -> dict:
    data = {
        "docker_cli": shutil.which("docker") is not None,
        "supported_services": sorted(set(SERVICE_COMMANDS)),
        "mode": "best-effort local control",
        "host_control_url": settings.host_control_url,
    }
    if include_remote:
        data["host_bridge"] = host_capabilities()
    return data


def start_service(service_name: str) -> dict:
    normalized = (service_name or "").strip().lower()
    command = SERVICE_COMMANDS.get(normalized)
    if not command:
        return {
            "ok": False,
            "message": f"Unknown service '{service_name}'. Supported: telegram, tg_bot, api.",
        }

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
        return {
            "ok": False,
            "message": f"Starting {normalized} timed out.",
        }
    except Exception as exc:
        return {
            "ok": False,
            "message": f"Failed to start {normalized}: {exc}",
        }


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

    if any(phrase in normalized for phrase in telegram_phrases):
        result = start_service("telegram")
        return result["message"]

    if any(phrase in normalized for phrase in api_phrases):
        result = start_service("api")
        return result["message"]

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
        response = requests.request(
            method,
            f"{settings.host_control_url}{path}",
            headers=headers,
            timeout=15,
        )
        data = response.json()
        if isinstance(data, dict):
            data.setdefault("ok", response.ok)
            return data
        return {"ok": response.ok, "message": str(data)}
    except Exception as exc:
        return {"ok": False, "message": f"Host control unavailable: {exc}"}
