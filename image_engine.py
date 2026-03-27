import hashlib
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import settings


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int):
    words = text.split()
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_local_image(prompt: str) -> str:
    prompt = (prompt or "").strip() or "Aiya"
    temp_dir = Path(tempfile.gettempdir()) / "aiya_images"
    temp_dir.mkdir(parents=True, exist_ok=True)
    filename = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:16] + ".png"
    out_path = temp_dir / filename

    width, height = 1024, 1024
    image = Image.new("RGB", (width, height), "#edfdf2")
    draw = ImageDraw.Draw(image)

    for y in range(height):
        mix = y / height
        r = int(237 * (1 - mix) + 14 * mix)
        g = int(253 * (1 - mix) + 84 * mix)
        b = int(242 * (1 - mix) + 46 * mix)
        draw.line((0, y, width, y), fill=(r, g, b))

    draw.ellipse((130, 120, 890, 880), outline="#dfffe9", width=12, fill="#f9fff9")
    draw.ellipse((230, 220, 430, 420), fill="#1e8a53")
    draw.ellipse((594, 220, 794, 420), fill="#1e8a53")
    draw.rounded_rectangle((330, 600, 694, 650), radius=20, fill="#208e57")
    draw.arc((180, 60, 840, 520), start=180, end=360, fill="#8cffb0", width=10)

    try:
        title_font = ImageFont.truetype("arial.ttf", 46)
        body_font = ImageFont.truetype("arial.ttf", 30)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    title = "AIYA // IMAGE MODE"
    draw.text((width // 2, 80), title, anchor="mm", fill="#0c4125", font=title_font)

    lines = _wrap_text(draw, prompt, body_font, 760)
    y = 740
    for line in lines[:6]:
        draw.text((width // 2, y), line, anchor="mm", fill="#08331d", font=body_font)
        y += 42

    draw.text(
        (width // 2, 960),
        f"profile={settings.performance.name} | palette=white-green",
        anchor="mm",
        fill="#145c35",
        font=body_font,
    )

    image.save(out_path, format="PNG")
    return str(out_path)
