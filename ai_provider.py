import requests

from config import settings


def _coerce_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif "content" in item:
                    parts.append(str(item.get("content", "")))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part).strip()
    return str(value).strip()


def _is_openai_compatible() -> bool:
    return settings.llm_provider == "openai_compatible"


def _auth_headers() -> dict[str, str]:
    if not settings.llm_api_key:
        return {}
    return {"Authorization": f"Bearer {settings.llm_api_key}"}


def chat_completion(
    prompt: str,
    model: str | None = None,
    format: str = "",
    timeout_seconds: int | None = None,
    temperature: float | None = None,
    num_predict: int | None = None,
) -> str:
    if _is_openai_compatible():
        return _chat_openai_compatible(
            prompt=prompt,
            model=model or settings.chat_model,
            format=format,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            num_predict=num_predict,
        )
    return _chat_ollama(
        prompt=prompt,
        model=model or settings.chat_model,
        format=format,
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        num_predict=num_predict,
    )


def embedding(text: str) -> list[float]:
    if _is_openai_compatible():
        return _embedding_openai_compatible(text)
    return _embedding_ollama(text)


def vision_completion(image_b64: str, instruction: str) -> str:
    if _is_openai_compatible():
        return _vision_openai_compatible(image_b64, instruction)
    return _vision_ollama(image_b64, instruction)


def _chat_ollama(
    prompt: str,
    model: str,
    format: str,
    timeout_seconds: int | None,
    temperature: float | None,
    num_predict: int | None,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.35 if temperature is None else temperature,
            "top_p": 0.9,
            "num_predict": num_predict or 180,
        },
    }
    if format == "json":
        payload["format"] = "json"
        payload["options"]["temperature"] = 0.1
        payload["options"]["num_predict"] = min(num_predict or 120, 120)
    response = requests.post(
        f"{settings.ollama_host}/api/generate",
        json=payload,
        timeout=timeout_seconds or settings.performance.llm_timeout_seconds,
    )
    response.raise_for_status()
    return _coerce_text(response.json().get("response", ""))


def _chat_openai_compatible(
    prompt: str,
    model: str,
    format: str,
    timeout_seconds: int | None,
    temperature: float | None,
    num_predict: int | None,
) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.35 if temperature is None else temperature,
    }
    if num_predict:
        payload["max_tokens"] = num_predict
    if format == "json":
        payload["response_format"] = {"type": "json_object"}
        payload["temperature"] = 0.1
        payload["max_tokens"] = min(num_predict or 120, 120)
    response = requests.post(
        f"{settings.llm_base_url}/chat/completions",
        json=payload,
        headers=_auth_headers(),
        timeout=timeout_seconds or settings.performance.llm_timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return _coerce_text(message.get("content", ""))


def _embedding_ollama(text: str) -> list[float]:
    payloads = [
        (f"{settings.ollama_host}/api/embed", {"model": settings.embed_model, "input": text}),
        (f"{settings.ollama_host}/api/embeddings", {"model": settings.embed_model, "prompt": text}),
    ]
    last_error = None
    for url, payload in payloads:
        try:
            response = requests.post(url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            if isinstance(data.get("embeddings"), list) and data["embeddings"]:
                return data["embeddings"][0]
            if isinstance(data.get("embedding"), list):
                return data["embedding"]
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Ollama embedding request failed: {last_error}")


def _embedding_openai_compatible(text: str) -> list[float]:
    if not settings.embed_model:
        return [0.0] * 768
    response = requests.post(
        f"{settings.llm_base_url}/embeddings",
        json={"model": settings.embed_model, "input": text},
        headers=_auth_headers(),
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    items = data.get("data") or []
    if not items:
        return [0.0] * 768
    return items[0].get("embedding") or [0.0] * 768


def _vision_ollama(image_b64: str, instruction: str) -> str:
    response = requests.post(
        f"{settings.ollama_host}/api/generate",
        json={
            "model": settings.vision_model,
            "prompt": instruction,
            "images": [image_b64],
            "stream": False,
        },
        timeout=settings.performance.llm_timeout_seconds,
    )
    response.raise_for_status()
    return _coerce_text(response.json().get("response", ""))


def _vision_openai_compatible(image_b64: str, instruction: str) -> str:
    if not settings.vision_model:
        return ""
    data_url = f"data:image/jpeg;base64,{image_b64}"
    payload = {
        "model": settings.vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0.2,
    }
    response = requests.post(
        f"{settings.llm_base_url}/chat/completions",
        json=payload,
        headers=_auth_headers(),
        timeout=settings.performance.llm_timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return _coerce_text(message.get("content"))
