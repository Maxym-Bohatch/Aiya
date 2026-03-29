import asyncio
import base64

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile

from config import settings

if not settings.telegram_token:
    raise RuntimeError("TELEGRAM_TOKEN is not configured")

ASK_URL = f"{settings.api_url}/ask"
FEATURES_URL = f"{settings.api_url}/users"
IMAGE_URL = f"{settings.api_url}/image/generate"
IMAGE_FILE_URL = f"{settings.api_url}/image/file"
SPEECH_URL = f"{settings.api_url}/speech/file"
SPEECH_TRANSCRIBE_URL = f"{settings.api_url}/speech/transcribe"
SPEECH_CAPABILITIES_URL = f"{settings.api_url}/speech/capabilities"
ACCOUNT_LINK_URL = f"{settings.api_url}/account/link/consume"

FEATURE_COMMANDS = {
    "tts": "tts_enabled",
    "emoji": "emoji_enabled",
    "ocr": "ocr_enabled",
    "subtitles": "desktop_subtitles_enabled",
    "image": "image_generation_enabled",
}

bot = Bot(token=settings.telegram_token)
dp = Dispatcher()


async def patch_features(message: types.Message, field: str, enabled: bool):
    url = f"{FEATURES_URL}/telegram/{message.from_user.id}/features"
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, json={field: enabled}, timeout=60) as response:
            if response.status != 200:
                return f"Не змогла оновити {field}: {response.status}"
            data = await response.json()
            return f"{field} => {data.get(field)}"


async def get_features(message: types.Message):
    url = f"{FEATURES_URL}/telegram/{message.from_user.id}/features"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=60) as response:
            if response.status != 200:
                return f"Не змогла отримати feature flags: {response.status}"
            data = await response.json()
            lines = ["Поточні feature flags:"]
            for key in sorted(data):
                lines.append(f"- {key}: {data[key]}")
            return "\n".join(lines)


async def get_tts_status():
    async with aiohttp.ClientSession() as session:
        async with session.get(SPEECH_CAPABILITIES_URL, timeout=60) as response:
            if response.status != 200:
                return "TTS capabilities недоступні."
            payload = await response.json()
            return (
                "TTS capabilities:\n"
                f"- provider: {payload.get('provider')}\n"
                f"- voice: {payload.get('voice')}\n"
                f"- delivery_enabled: {payload.get('delivery_enabled')}\n"
                f"- edge_available: {payload.get('edge_available')}"
            )


async def send_speech_reply(message: types.Message, session: aiohttp.ClientSession, text: str):
    async with session.post(SPEECH_URL, json={"text": text}, timeout=180) as response:
        if response.status != 200:
            detail = await response.text()
            await message.answer(f"TTS недоступний: {detail}")
            return
        audio_bytes = await response.read()
        content_type = (response.headers.get("Content-Type") or "").lower()

    if "ogg" in content_type:
        voice = BufferedInputFile(audio_bytes, filename="aiya_reply.ogg")
        await message.answer_voice(voice, caption="Голос Айї")
        return
    if "mpeg" in content_type or "mp3" in content_type:
        audio = BufferedInputFile(audio_bytes, filename="aiya_reply.mp3")
        await message.answer_audio(audio, caption="Голос Айї")
        return
    audio = BufferedInputFile(audio_bytes, filename="aiya_reply.wav")
    await message.answer_audio(audio, caption="Голос Айї")


async def generate_and_send_image(message: types.Message, prompt: str):
    prompt = (prompt or "").strip()
    if not prompt:
        await message.answer("Використання: /image <опис картинки>")
        return

    async with aiohttp.ClientSession() as session:
        async with session.post(IMAGE_FILE_URL, json={"prompt": prompt}, timeout=180) as response:
            if response.status == 200:
                image_bytes = await response.read()
                image = BufferedInputFile(image_bytes, filename="aiya_image.png")
                await message.answer_photo(image, caption=f"Картинка для: {prompt}")
                return

        async with session.post(IMAGE_URL, json={"prompt": prompt}, timeout=180) as response:
            if response.status != 200:
                detail = await response.text()
                await message.answer(f"Генерація картинки недоступна: {detail}")
                return
            data = await response.json()
            await message.answer(f"Картинку згенеровано. Відповідь бекенда: {data}")


async def _download_telegram_audio(message: types.Message) -> tuple[bytes, str, str]:
    source = message.voice or message.audio
    if source is None:
        raise RuntimeError("No audio attachment was found.")
    file = await bot.get_file(source.file_id)
    handle = await bot.download_file(file.file_path)
    filename = getattr(source, "file_name", "") or ("voice.ogg" if message.voice else "audio.bin")
    content_type = "audio/ogg" if filename.lower().endswith(".ogg") else "audio/mpeg"
    return handle.read(), filename, content_type


async def transcribe_audio_message(message: types.Message, session: aiohttp.ClientSession) -> str:
    audio_bytes, filename, content_type = await _download_telegram_audio(message)
    async with session.post(
        SPEECH_TRANSCRIBE_URL,
        json={
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "filename": filename,
            "content_type": content_type,
        },
        timeout=240,
    ) as response:
        if response.status != 200:
            detail = await response.text()
            raise RuntimeError(detail)
        payload = await response.json()
        return (payload.get("text") or "").strip()


@dp.message(Command("features"))
async def handle_features(message: types.Message):
    await message.answer(await get_features(message))


@dp.message(Command("tts_status"))
async def handle_tts_status(message: types.Message):
    await message.answer(await get_tts_status())


@dp.message(Command("speak"))
async def handle_speak(message: types.Message, command: CommandObject):
    text = (command.args or "").strip()
    if not text:
        await message.answer("Використання: /speak текст для озвучення")
        return
    async with aiohttp.ClientSession() as session:
        await send_speech_reply(message, session, text)


@dp.message(Command("link"))
async def handle_link(message: types.Message, command: CommandObject):
    code = (command.args or "").strip().upper()
    if not code:
        await message.answer("Використання: /link CODE")
        return
    async with aiohttp.ClientSession() as session:
        async with session.post(
            ACCOUNT_LINK_URL,
            json={
                "platform": "telegram",
                "external_id": message.from_user.id,
                "user_name": message.from_user.first_name or "TelegramUser",
                "code": code,
            },
            timeout=60,
        ) as response:
            data = await response.json()
            if response.status != 200:
                await message.answer(f"Не вдалося прив'язати акаунт: {data.get('detail', response.status)}")
                return
            linked = ", ".join(f"{item['platform']}:{item['external_id']}" for item in data.get("linked_identities", []))
            await message.answer(f"Акаунти об'єднано. Тепер прив'язки: {linked}")


@dp.message(Command("help"))
async def handle_help(message: types.Message):
    await message.answer(
        "Команди:\n"
        "/features\n"
        "/tts on|off\n"
        "/tts_status\n"
        "/speak <текст>\n"
        "/emoji on|off\n"
        "/ocr on|off\n"
        "/subtitles on|off\n"
        "/image on|off\n"
        "/image <prompt>\n"
        "/link <code>"
    )


@dp.message(Command(*FEATURE_COMMANDS.keys()))
async def handle_feature_toggle(message: types.Message, command: CommandObject):
    name = command.command.lower()
    raw_arg = (command.args or "").strip()
    arg = raw_arg.lower()
    if name == "image" and arg and arg not in {"on", "off"}:
        await generate_and_send_image(message, raw_arg)
        return
    if arg not in {"on", "off"}:
        await message.answer(f"Використання: /{name} on або /{name} off")
        return
    result = await patch_features(message, FEATURE_COMMANDS[name], arg == "on")
    await message.answer(result)


@dp.message()
async def handle_tg_message(message: types.Message):
    safe_text = (message.text or "").strip()
    if message.voice or message.audio:
        try:
            async with aiohttp.ClientSession() as session:
                safe_text = await transcribe_audio_message(message, session)
            if not safe_text:
                await message.answer("Не вдалося розпізнати текст із голосового повідомлення.")
                return
            await message.answer(f"Розпізнано: {safe_text}")
        except Exception as exc:
            await message.answer(f"Голосове повідомлення не оброблено: {exc}")
            return
    if not safe_text:
        await message.answer("Я поки реагую лише на текстові повідомлення.")
        return

    lowered = safe_text.lower()
    if lowered.startswith("/image "):
        await generate_and_send_image(message, safe_text[7:].strip())
        return

    user_token = safe_text if safe_text == settings.admin_token else ""
    if user_token:
        await message.answer("Адмінський токен прийнято. Тепер надішли окремим повідомленням сам запит.")
        return
    headers = {"X-Aiya-Token": user_token}
    payload = {
        "platform": "telegram",
        "external_id": message.from_user.id,
        "user_name": message.from_user.first_name or "Користувач",
        "text": safe_text,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ASK_URL, json=payload, headers=headers, timeout=180) as response:
                if response.status != 200:
                    await message.answer(f"API помилка: {response.status}")
                    return
                data = await response.json()
                answer = data.get("answer", "Айя мовчить.")
                await message.answer(answer)

                if data.get("tts_available"):
                    await send_speech_reply(message, session, answer)
    except Exception as exc:
        await message.answer(f"Помилка зв'язку з ядром: {exc}")


async def main():
    try:
        print("Telegram bot started")
        await dp.start_polling(bot)
    except TelegramUnauthorizedError:
        print("Telegram bot token is invalid. Fix TELEGRAM_TOKEN in .env and restart the bot.")
        await asyncio.sleep(300)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Telegram bot stopped")
