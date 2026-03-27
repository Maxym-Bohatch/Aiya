import asyncio

import aiohttp
from aiogram import Bot, Dispatcher, types
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


@dp.message(Command("features"))
async def handle_features(message: types.Message):
    await message.answer(await get_features(message))


@dp.message(Command("help"))
async def handle_help(message: types.Message):
    await message.answer(
        "Команди:\n"
        "/features\n"
        "/tts on|off\n"
        "/emoji on|off\n"
        "/ocr on|off\n"
        "/subtitles on|off\n"
        "/image on|off\n"
        "/image <prompt>"
    )


@dp.message(Command(*FEATURE_COMMANDS.keys()))
async def handle_feature_toggle(message: types.Message, command: CommandObject):
    name = command.command.lower()
    arg = (command.args or "").strip().lower()
    if arg not in {"on", "off"}:
        await message.answer(f"Використання: /{name} on або /{name} off")
        return
    result = await patch_features(message, FEATURE_COMMANDS[name], arg == "on")
    await message.answer(result)


@dp.message()
async def handle_tg_message(message: types.Message):
    safe_text = (message.text or "").strip()
    if not safe_text:
        await message.answer("Я поки реагую лише на текстові повідомлення.")
        return

    lowered = safe_text.lower()
    if lowered.startswith("/image "):
        prompt = safe_text[7:].strip()
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
        return

    user_token = safe_text if safe_text == settings.admin_token else ""
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
                    async with session.post(SPEECH_URL, json={"text": answer}, timeout=180) as speech_response:
                        if speech_response.status == 200:
                            audio_bytes = await speech_response.read()
                            content_type = (speech_response.headers.get("Content-Type") or "").lower()
                            if "ogg" in content_type:
                                audio = BufferedInputFile(audio_bytes, filename="aiya_reply.ogg")
                                await message.answer_voice(audio, caption="Голос Айї")
                            elif "mpeg" in content_type or "mp3" in content_type:
                                audio = BufferedInputFile(audio_bytes, filename="aiya_reply.mp3")
                                await message.answer_audio(audio, caption="Голос Айї")
                            else:
                                audio = BufferedInputFile(audio_bytes, filename="aiya_reply.wav")
                                await message.answer_audio(audio, caption="Голос Айї")
    except Exception as e:
        await message.answer(f"Помилка зв'язку з ядром: {e}")


async def main():
    print("Telegram bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Telegram bot stopped")
