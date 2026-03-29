import time

import requests

from config import settings


OLLAMA_TAGS_URL = f"{settings.ollama_host}/api/tags"
OLLAMA_PULL_URL = f"{settings.ollama_host}/api/pull"


def is_ollama_model_name(name: str) -> bool:
    value = (name or "").strip().lower()
    if not value:
        return False
    # "deep_translator" and similar identifiers are app-level backends, not Ollama tags.
    if value in {"auto", "deep_translator", "deep-translator", "google", "google_translate"}:
        return False
    return ":" in value or "/" in value


def wait_for_ollama(timeout_seconds=300):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(OLLAMA_TAGS_URL, timeout=10)
            if response.ok:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def installed_models():
    response = requests.get(OLLAMA_TAGS_URL, timeout=20)
    response.raise_for_status()
    data = response.json()
    return {model["name"] for model in data.get("models", [])}


def pull_model(name: str):
    if not name:
        return
    response = requests.post(
        OLLAMA_PULL_URL,
        json={"name": name, "stream": False},
        timeout=3600,
    )
    response.raise_for_status()


def main():
    if settings.llm_provider != "ollama":
        print("Skipping Ollama bootstrap because an external API provider is configured.")
        return

    if not wait_for_ollama():
        raise RuntimeError("Ollama is not reachable")

    desired = {
        settings.ollama_chat_model,
        settings.ollama_embed_model,
        settings.ollama_vision_model,
        settings.translation_model,
    }
    desired = {model for model in desired if is_ollama_model_name(model)}
    existing = installed_models()
    missing = [model for model in desired if model and model not in existing]

    if not missing:
        print("All required Ollama models are already installed.")
        return

    for model in missing:
        print(f"Pulling model: {model}")
        pull_model(model)

    print("Model bootstrap complete.")


if __name__ == "__main__":
    main()
