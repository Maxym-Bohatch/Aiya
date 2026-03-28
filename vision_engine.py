import base64
import io

import requests
from PIL import Image

import ai_provider
from config import settings


def _resize_base64_image(image_b64: str, max_side: int = 896) -> str:
    raw = base64.b64decode(image_b64)
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    width, height = image.size
    scale = min(1.0, max_side / max(width, height))
    if scale < 1.0:
        image = image.resize((int(width * scale), int(height * scale)))
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=85)
    return base64.b64encode(out.getvalue()).decode("utf-8")


def analyze_image(image_b64: str, instruction: str = "") -> str:
    if not settings.enable_vision:
        return ""

    prompt = instruction.strip() or (
        "Опиши коротко, що відбувається на екрані. "
        "Зверни увагу на гру, інтерфейс, важливі кнопки, повідомлення і стан сцени."
    )
    try:
        prepared = _resize_base64_image(image_b64)
        return ai_provider.vision_completion(prepared, prompt)
    except Exception as e:
        print(f"Vision error: {e}")
        return ""
