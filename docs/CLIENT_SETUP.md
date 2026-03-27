# Client Setup

1. Build the client EXE on the main workspace PC:
   - `scripts/client/build_client_exe.ps1`
   - `scripts/client/package_client_bundle.ps1`
2. Copy only `release/client_bundle` to the client PC.
3. Rename `.env.client.example` to `.env.client` and edit the URLs/tokens.
4. Launch `AiyaClientLauncher.exe`.
5. Use the launcher tabs to:
   - check client setup
   - save config
   - open the desktop companion window
   - ping API / host bridge
   - manage desktop feature flags
   - install OCR language packs for Tesseract
   - use the wiki tab
6. If you run from source instead of the packaged EXE, use `scripts/client/install_client_prereqs.ps1` first.
7. For game mode, open the companion, set the game name, switch to `Screen Always`, then enable `Game On/Off`.

Recommended split:
- Server PC: Docker, Ollama, PostgreSQL, Telegram, backend, rebuild scripts
- Client PC: only the packaged client bundle
- Client PC OCR needs local Tesseract installed on that same PC
- Client PC translation uses the backend API, but OCR language packs still live on the client Tesseract install
- `AIYA_CHARACTER_ASSET` can point to your own GIF/PNG or a folder with `manifest.json` + `idle.gif`

Do not copy these server-only paths to the client PC:
- `postgres_data`
- `ollama_storage`
- `open_webui`
- `docker-compose.yml`
- `Dockerfile`
- `scripts/server`
