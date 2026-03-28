import json
import os
import shutil
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psycopg2

from installer.update_manager import update_installation

PROJECT_DIR = Path(__file__).resolve().parent
ENV_PATH = PROJECT_DIR / ".env"
HOST = os.getenv("HOST_CONTROL_BIND", "0.0.0.0")
PORT = int(os.getenv("HOST_CONTROL_PORT", "8765"))
CURRENT_TOKEN = (os.getenv("HOST_CONTROL_TOKEN") or os.getenv("AIYA_ADMIN_TOKEN") or "").strip()
ALLOWED_CONFIG_KEYS = {
    "AIYA_ADMIN_TOKEN",
    "AIYA_EXTRA_ADMIN_TOKENS",
    "HOST_CONTROL_TOKEN",
    "TELEGRAM_TOKEN",
    "DB_PASSWORD",
    "AIYA_LLM_MODE",
    "AIYA_LLM_PROVIDER",
    "AIYA_LLM_BASE_URL",
    "AIYA_LLM_API_KEY",
    "OLLAMA_HOST",
    "API_URL",
    "HOST_CONTROL_URL",
    "AIYA_TTS_PROVIDER",
    "AIYA_TTS_PRESET",
    "AIYA_TTS_RATE",
    "AIYA_TTS_PITCH",
    "AIYA_ALLOW_LOCAL_TTS",
    "TTS_VOICE",
    "AIYA_PERFORMANCE_PROFILE",
    "OLLAMA_CHAT_MODEL",
    "OLLAMA_EMBED_MODEL",
    "OLLAMA_VISION_MODEL",
    "AIYA_TRANSLATION_MODEL",
    "AIYA_TTS_PROVIDER",
    "TTS_VOICE",
    "AIYA_TTS_RATE",
    "AIYA_TTS_PITCH",
    "AIYA_ALLOW_LOCAL_TTS",
    "TRANSLATION_BACKEND_URL",
    "TTS_BACKEND_URL",
}
FAST_START_CONTAINERS = {
    "telegram": ["aiya_core", "aiya_tg"],
    "tg_bot": ["aiya_tg"],
    "api": ["aiya_core"],
    "web": ["aiya_core", "aiya_open_webui"],
}


def service_command(service_name: str) -> list[str] | None:
    if service_name == "web" and current_llm_mode() == "external_api":
        return None
    mapping = {
        "telegram": ["up", "-d", "api", "tg_bot"],
        "tg_bot": ["up", "-d", "api", "tg_bot"],
        "api": ["up", "-d", "api"],
        "web": ["up", "-d", "api", "webui"],
    }
    args = mapping.get(service_name)
    if not args:
        return None
    return [*compose_command_base(), *args]


def supported_services() -> list[str]:
    services = ["api", "tg_bot", "telegram"]
    if current_llm_mode() != "external_api":
        services.append("web")
    return services


def current_llm_mode() -> str:
    current = read_env_file()
    mode = (current.get("AIYA_LLM_MODE") or "bundled_ollama").strip().lower()
    if mode in {"bundled_ollama", "external_ollama", "external_api"}:
        return mode
    return "bundled_ollama"


def compose_command_base() -> list[str]:
    mode = current_llm_mode()
    if mode == "external_ollama":
        return ["docker", "compose", "-f", "docker-compose.external-ollama.yml"]
    if mode == "external_api":
        return ["docker", "compose", "-f", "docker-compose.external-api.yml"]
    return ["docker", "compose", "-f", "docker-compose.yml"]


def read_env_file() -> dict[str, str]:
    values = {}
    if not ENV_PATH.exists():
        return values
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def write_env_file(values: dict[str, str]):
    lines = [f"{key}={values[key]}" for key in sorted(values)]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_command(command: list[str]) -> tuple[bool, str]:
    if shutil.which("docker") is None and command[:1] == ["docker"]:
        return False, "Docker CLI is not available on the host."
    try:
        completed = subprocess.run(command, cwd=PROJECT_DIR, capture_output=True, text=True, timeout=300, check=True)
        output = (completed.stdout or completed.stderr or "").strip()
        return True, output or "ok"
    except subprocess.TimeoutExpired:
        return False, "Command timed out."
    except subprocess.CalledProcessError as exc:
        output = (exc.stdout or exc.stderr or "").strip()
        return False, output or f"Command failed: {exc}"
    except Exception as exc:
        return False, str(exc)


def compose_status() -> tuple[bool, str]:
    return run_command([*compose_command_base(), "ps", "-a"])


def fast_start(service_name: str) -> tuple[bool, str]:
    containers = FAST_START_CONTAINERS.get(service_name, [])
    if not containers:
        return False, "No fast-start mapping."
    return run_command(["docker", "start", *containers])


def restart_impacted_services(changed_keys: set[str]) -> tuple[bool, str]:
    services = ["api"]
    if changed_keys.intersection({"TELEGRAM_TOKEN", "AIYA_ADMIN_TOKEN", "AIYA_EXTRA_ADMIN_TOKENS"}):
        services.append("tg_bot")
    return run_command([*compose_command_base(), "up", "-d", "--force-recreate", *services])


def rotate_database_password(old_password: str, new_password: str) -> tuple[bool, str]:
    if not old_password or not new_password:
        return False, "Old or new DB password is empty."
    try:
        connection = psycopg2.connect(
            host="127.0.0.1",
            port=5433,
            dbname="aiya_memory",
            user="maxim",
            password=old_password,
            connect_timeout=10,
        )
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("ALTER USER maxim WITH PASSWORD %s", (new_password,))
        connection.close()
        return True, "Database password rotated."
    except Exception as exc:
        return False, f"Database password rotation failed: {exc}"


def update_config_values(updates: dict, restart_services: bool) -> dict:
    global CURRENT_TOKEN

    current = read_env_file()
    normalized_updates = {key: str(value).strip() for key, value in updates.items() if key in ALLOWED_CONFIG_KEYS}
    if not normalized_updates:
        return {"ok": False, "message": "No allowed config keys were provided."}

    if "DB_PASSWORD" in normalized_updates:
        old_password = current.get("DB_PASSWORD", "")
        new_password = normalized_updates["DB_PASSWORD"]
        if old_password and old_password != new_password:
            ok, message = rotate_database_password(old_password, new_password)
            if not ok:
                return {"ok": False, "message": message}

    changed_keys = {key for key, value in normalized_updates.items() if current.get(key, "") != value}
    current.update(normalized_updates)
    write_env_file(current)

    if "HOST_CONTROL_TOKEN" in normalized_updates and normalized_updates["HOST_CONTROL_TOKEN"]:
        CURRENT_TOKEN = normalized_updates["HOST_CONTROL_TOKEN"]

    restart_result = {"ok": True, "message": "Restart not requested."}
    if restart_services and changed_keys:
        ok, message = restart_impacted_services(changed_keys)
        restart_result = {"ok": ok, "message": message}

    snapshot = {key: current.get(key, "") for key in sorted(ALLOWED_CONFIG_KEYS)}
    return {
        "ok": True,
        "changed_keys": sorted(changed_keys),
        "config": snapshot,
        "restart": restart_result,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "AiyaHostControl/2.0"

    def do_GET(self):
        if not self._authorized():
            return
        if self.path == "/health":
            self._json(HTTPStatus.OK, {"ok": True, "status": "ok"})
            return
        if self.path == "/capabilities":
            ok, status = compose_status()
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "docker_cli": shutil.which("docker") is not None,
                    "nvidia_smi": shutil.which("nvidia-smi") is not None,
                    "winget": shutil.which("winget") is not None,
                    "project_dir": str(PROJECT_DIR),
                    "supported_services": supported_services(),
                    "compose_status_ok": ok,
                    "compose_status": status,
                    "config_keys": sorted(ALLOWED_CONFIG_KEYS),
                },
            )
            return
        if self.path == "/config":
            current = read_env_file()
            snapshot = {key: current.get(key, "") for key in sorted(ALLOWED_CONFIG_KEYS)}
            self._json(HTTPStatus.OK, {"ok": True, "config": snapshot})
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "Not found"})

    def do_POST(self):
        if not self._authorized():
            return
        parts = [part for part in self.path.split("/") if part]
        if len(parts) == 3 and parts[0] == "services" and parts[2] == "start":
            service_name = parts[1].lower()
            command = service_command(service_name)
            if not command:
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "message": f"Unknown service '{service_name}'"})
                return
            ok, output = fast_start(service_name)
            if not ok:
                ok, output = run_command(command)
            code = HTTPStatus.OK if ok else HTTPStatus.SERVICE_UNAVAILABLE
            self._json(code, {"ok": ok, "service": service_name, "message": output})
            return
        if self.path == "/config/update":
            payload = self._read_json()
            result = update_config_values(payload.get("updates", {}), bool(payload.get("restart_services", True)))
            code = HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST
            self._json(code, result)
            return
        if self.path == "/update":
            try:
                result = update_installation(PROJECT_DIR)
                self._json(HTTPStatus.OK, result)
            except Exception as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "message": str(exc)})
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "message": "Not found"})

    def log_message(self, format: str, *args):
        return

    def _authorized(self) -> bool:
        if not CURRENT_TOKEN:
            self._json(HTTPStatus.FORBIDDEN, {"ok": False, "message": "HOST_CONTROL_TOKEN is not configured on host."})
            return False
        provided = (self.headers.get("X-Aiya-Host-Token") or "").strip()
        if provided != CURRENT_TOKEN:
            self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "message": "Invalid host control token."})
            return False
        return True

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Host control server listening on http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
