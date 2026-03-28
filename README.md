# Aiya

Aiya is now structured as a Docker-first local assistant backend with:

- long-term memory on PostgreSQL + pgvector
- Ollama for local LLM inference or an OpenAI-compatible external API
- Telegram as one client channel
- a built-in Aiya web UI on the local site
- Open WebUI as an optional second interaction channel
- per-user privacy boundaries
- per-user feature toggles for TTS, OCR, emoji, desktop subtitles, and image generation
- a separate host desktop companion for avatar, OCR, and floating subtitles
- a desktop client launcher for config, admin tokens, Docker bridge, wiki, and opening the companion window
- a dedicated server launcher for first-run `.env` setup, Docker Desktop checks, and one-click backend startup
- performance profiles for weaker and stronger PCs

## What works now

- `docker compose up --build` starts the core API, PostgreSQL, Ollama, Telegram bot, the Aiya local web UI, and optional Open WebUI
- external LLM mode can run against either another Ollama host or an OpenAI-compatible API
- each user gets isolated memory by default
- admin token and extra admin tokens can elevate the current user to level 10
- users can toggle features through API and basic Telegram commands:
  - `/tts on`
  - `/tts off`
  - `/ocr on`
  - `/ocr off`
  - `/emoji on`
  - `/emoji off`
- image generation and TTS are wired as pluggable backends via `IMAGE_BACKEND_URL` and `TTS_BACKEND_URL`
- higher-quality voice delivery works through `edge-tts` by default, with local fallback only when explicitly allowed
- Telegram can send Aiya voice replies when `tts_enabled` is on for that user
- `desktop_companion.py` gives a non-topmost `Core` control window plus detached subtitle and character overlays on the host machine
- `client/launcher.py` gives one GUI entry point for client config, health checks, admin token generation, Docker bridge control, wiki lookup, and opening the desktop companion
- from the launcher, an admin can rotate Telegram token, database password, host token, main admin token, and assign extra admin tokens for other trusted admins
- screen OCR can be stored as recent screen-context and mixed into Aiya's prompt
- screenshot vision analysis can use a local Ollama vision model when available
- game mode can observe the current screen summary and ask the core for next actions
- the companion translator uses the backend `/translate` API, so split deployment works correctly from another PC
- the client launcher can install extra Tesseract OCR language packs on the client PC
- the companion can load a custom on-screen character from `AIYA_CHARACTER_ASSET`
- local image generation can work even without a separate image backend
- optional virtual gamepad support is used when `vgamepad` is available on the host
- wiki lookup is available on the backend through a dedicated module and API
- Ollama models can be auto-bootstrapped on first compose startup

## Memory design

Aiya's memory is split into layers inspired by the SVINOPAS idea:

- chat history: recent raw dialogue for short conversational continuity
- facts memory: extracted facts stored with embeddings for semantic retrieval
- graph memory: entity-relation triples for fast associative recall
- alias memory: maps nicknames like `Макс` and `Максим` to one canonical identity
- screen memory: OCR observations and short summaries of what is happening on the user's screen
- game memory: observed scenes, planned actions, and outcomes for future gameplay learning
- wiki memory: cached factual context from Wikipedia for questions about people, places, concepts, and topics

There is also an internal "gnome council" prompt layer for facts, mood, graph memory, wiki context, and future robotics orchestration.

There is also a recall cooldown on facts so the assistant does not over-repeat the same memory fragment every turn.

## Important constraint

The desktop avatar, floating green subtitles on top of a model, and OCR screen watching cannot be truly Docker-only on their own, because they need host OS access. The practical architecture is:

1. Docker runs the brain, memory, API, Telegram, web UI, TTS/image services.
2. A thin desktop client connects to the API and handles:
   - avatar rendering
   - OCR/screen capture
   - desktop subtitles
   - optional TTS playback

## Run

Backend:

```bash
docker compose up --build
```

Easy mode on Windows:

```powershell
.\start_aiya.ps1
```

Split mode:

```powershell
.\start_server_only.ps1
.\start_client_only.ps1
```

On first start, the `ollama_setup` service will try to pull the required text, embedding, and vision models.

Desktop server launcher on the host:

```bash
AiyaServerLauncher.exe
```

Desktop client launcher on the host:

```bash
python -m client.launcher
```

Direct legacy companion entry point still exists:

```bash
python desktop_companion.py
```

Hotkeys in desktop companion:

- `F8`: capture screen once
- `F9`: toggle OCR
- `F10`: toggle game mode
- `F11`: choose a translation area

Custom companion character:

- set `AIYA_CHARACTER_ASSET` to a `.gif`, `.png`, `.webp`, `.jpg`, or a folder with `manifest.json` + `idle.gif`
- set `AIYA_CHARACTER_DOCK=left` or `right`
- subtitles stay in a light-green overlay near the bottom of the screen

## Workspace layout

- `client/`
  - client-side launcher helpers
- `scripts/client/`
  - client launcher start
  - client `.exe` build
  - client bundle packaging
  - full Windows release build
- `scripts/server/`
  - server start
  - Docker rebuild
- `installer/`
  - GitHub bootstrap installer
  - uninstaller
- `docs/`
  - client setup
  - Docker migration notes
  - installer notes

## First-start checklist

1. Copy `.env.example` to `.env`.
2. Fill in:
   - `TELEGRAM_TOKEN`
   - `DB_PASSWORD`
   - `AIYA_ADMIN_TOKEN`
  - optional: `AIYA_EXTRA_ADMIN_TOKENS=token_for_admin2,token_for_admin3`
3. Pick performance:
   - weak machine: `AIYA_PERFORMANCE_PROFILE=low`
   - normal machine: `AIYA_PERFORMANCE_PROFILE=balanced`
   - strong machine: `AIYA_PERFORMANCE_PROFILE=high`
   - unsure: leave `auto`
4. Choose LLM mode:
   - bundled Ollama: keep `AIYA_LLM_MODE=bundled_ollama` and `AIYA_LLM_PROVIDER=ollama`
   - external Ollama: set `AIYA_LLM_MODE=external_ollama`, `AIYA_LLM_PROVIDER=ollama`, and point `OLLAMA_HOST` to that server
   - external API: set `AIYA_LLM_MODE=external_api`, `AIYA_LLM_PROVIDER=openai_compatible`, then fill `AIYA_LLM_BASE_URL` and `AIYA_LLM_API_KEY`
5. Optional model overrides:
   - `OLLAMA_CHAT_MODEL`
   - `OLLAMA_EMBED_MODEL`
   - `OLLAMA_VISION_MODEL`
6. Start Docker:

```bash
docker compose up --build
```

   Or on Windows use:

```powershell
.\start_aiya.ps1
```

7. Wait until:
   - `db` is healthy
   - in bundled Ollama mode: `ollama` is up and `ollama_setup` finishes successfully
   - `api` and `tg_bot` are running
   - `webui` is running only in Ollama-based modes
8. Open interfaces:
   - API health: `http://localhost:8000/health`
   - Aiya web UI: `http://localhost:3000`
   - Open WebUI (optional, direct Ollama UI): `http://localhost:3001` in Ollama-based modes
9. Start desktop body on host:

```bash
python -m client.launcher
```

To stop everything cleanly on Windows:

```powershell
.\stop_aiya.ps1
```

## Self-healing and host control

- `start_aiya.ps1` starts the host control bridge and then runs `docker compose up -d --build`
- `host_control_server.py` runs on the host and can start local Docker services for Aiya
- from the Aiya web UI or API, commands like `підніми телеграм` can ask the host bridge to start `api` + `tg_bot`
- the host bridge uses `HOST_CONTROL_TOKEN`; if it is missing, `start_aiya.ps1` copies `AIYA_ADMIN_TOKEN` into it
- inside Docker, Aiya reaches the host bridge through `HOST_CONTROL_URL=http://host.docker.internal:8765`

## Split deployment

- server PC: run Docker, PostgreSQL, API, Telegram bot, and either bundled Ollama, external Ollama, or an external API
- client PC: run only `desktop_companion.py`, browser, OCR/avatar/game-control side
- client PC: preferably run only the packaged launcher bundle (`AiyaClientLauncher.exe`) and browser
- you do not need to change `localhost` defaults in code; use a separate `.env.client` on the client machine
- example client env:

```env
API_URL=http://192.168.0.10:8000
REMOTE_WEB_URL=http://192.168.0.10:3000
REMOTE_OPEN_WEBUI_URL=http://192.168.0.10:3001
```

- on the server machine you can keep the normal `.env` or create `.env.server`
- convenient scripts:
  - `.\start_server_only.ps1` for the Docker/server side
  - `.\start_client_only.ps1` for the desktop client side
- build and package the client:
  - `.\scripts\client\build_client_exe.ps1`
  - `.\scripts\client\package_client_bundle.ps1`
- build full Windows release:
  - `.\scripts\client\build_windows_release.ps1`
- rebuild Docker intentionally:
  - `.\scripts\server\rebuild_docker.ps1`
- best layout:
  - server PC: `db`, `ollama`, `api`, `tg_bot`, optional `webui`
  - client PC: `AiyaClientLauncher.exe` and browser
- if you use OCR, game mode, subtitles, or avatar tied to your screen, the desktop client must run on the PC whose screen you are actually using

## Robot Bridge

- `GET /robot/capabilities`
- `GET /robot/state`
- `PATCH /robot/state`
- `POST /robot/sensors`
- `GET /robot/sensors/recent`
- `POST /robot/commands`
- `GET /robot/commands/next?target=body-controller`
- `POST /robot/commands/{id}/complete`

This bridge is intended as the stable integration layer for future physical hardware: cameras, IMU sensors, telemetry, manipulators, locomotion controllers, docking logic, and other actuator modules. The goal is that you can connect external controller code to these endpoints without rewriting Aiya core.

See the dedicated integration guide in [docs/ROBOT_BRIDGE.md](docs/ROBOT_BRIDGE.md).

## Coding help

- Aiya is now instructed to act as a practical coding assistant for code questions
- Python and Java are explicitly prioritized in her base response rules
- ask in the web UI or Telegram with prompts like:
  - `напиши Python-скрипт для перейменування файлів`
  - `поясни цей Java exception`
  - `зроби простий REST API на FastAPI`

## Recommended model presets

Low:

```env
AIYA_PERFORMANCE_PROFILE=low
OLLAMA_CHAT_MODEL=qwen2.5:1.5b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_VISION_MODEL=llava:7b
```

Balanced:

```env
AIYA_PERFORMANCE_PROFILE=balanced
OLLAMA_CHAT_MODEL=qwen2.5:3b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_VISION_MODEL=llava:7b
```

High:

```env
AIYA_PERFORMANCE_PROFILE=high
OLLAMA_CHAT_MODEL=qwen2.5:7b
OLLAMA_EMBED_MODEL=nomic-embed-text
OLLAMA_VISION_MODEL=llava:13b
```

## Performance profiles

Set `AIYA_PERFORMANCE_PROFILE` to one of:

- `low`: weak CPU-first systems
- `balanced`: normal everyday machines
- `high`: stronger machines

If left as `auto`, Aiya picks a profile from detected hardware hints.

## Suggested next build phases

1. Add a lightweight desktop client, for example Tauri or Electron, for the avatar and subtitles.
2. Upgrade OCR from text-only to full image understanding with a local vision model.
3. Upgrade TTS from `espeak-ng` fallback to a more expressive neural local voice.
4. Add a heavier local image generation container, for example ComfyUI, and connect it through `IMAGE_BACKEND_URL`.
5. Replace keyboard-first game control with richer game-specific controller policies.

## Environment

Example additions for `.env`:

```env
ENABLE_TTS=true
ENABLE_OCR=false
ENABLE_IMAGE_GENERATION=false
ENABLE_DESKTOP_SUBTITLES=true
ENABLE_EMOJI=true
ENABLE_SCREEN_CONTEXT=true
ENABLE_GAME_MODE=true
ENABLE_VISION=true
ENABLE_WIKI=true
AIYA_PERFORMANCE_PROFILE=auto
AIYA_HARDWARE_CLASS=
OLLAMA_CHAT_MODEL=
OLLAMA_EMBED_MODEL=
OLLAMA_VISION_MODEL=
TTS_BACKEND_URL=
IMAGE_BACKEND_URL=
TTS_VOICE=uk+f3
```

## API

- `GET /health`
- `GET /`
- `GET /ui`
- `POST /ask`
- `GET /users/{platform}/{external_id}/features`
- `PATCH /users/{platform}/{external_id}/features`
- `POST /consent`
- `POST /image/generate`
- `POST /speech/synthesize`
- `POST /speech/file`
- `POST /users/{platform}/{external_id}/aliases`
- `POST /screen/observe`
- `POST /screen/analyze-image`
- `POST /game/plan`
- `GET /game/capabilities`
- `GET /control/capabilities`
- `POST /control/services/{service_name}/start`
- `POST /control/services/{service_name}/restart`
- `GET /wiki/capabilities`
- `POST /wiki/search`
- `POST /image/file`

## Installer

- `AiyaInstaller.exe` downloads the selected GitHub branch and installs:
  - `client`
  - `server`
  - `both`
- installed server and both modes now include `AiyaServerLauncher.exe` for first-run `.env` setup, Docker install help, and backend start/stop without opening a console
- for server installs it can:
  - check `docker`, `winget`, `wsl`
  - launch Docker Desktop installation
- `AiyaUninstaller.exe` is copied into the install folder and can remove app files while optionally preserving env files and Docker data
- after install, use `AiyaServerLauncher.exe` to fill the required server `.env` on the first run and start Docker
- after install, use `AiyaClientLauncher.exe` with the host token to rotate Telegram token, DB password, and assign extra admin tokens remotely
