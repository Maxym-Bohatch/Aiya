# Client Setup

1. Build the client EXE on the main workspace PC:
   - `scripts/client/build_client_exe.ps1`
   - `scripts/client/package_client_bundle.ps1`
2. Copy only `release/client_bundle` to the client PC.
3. Rename `.env.client.example` to `.env.client` and edit the URLs/tokens.
4. Launch `AiyaClientLauncher.exe`.
5. Use the launcher tabs to:
   - save config
   - open the desktop companion window
   - ping API / host bridge
   - manage desktop feature flags
   - use the wiki tab

Recommended split:
- Server PC: Docker, Ollama, PostgreSQL, Telegram, backend, rebuild scripts
- Client PC: only the packaged client bundle

Do not copy these server-only paths to the client PC:
- `postgres_data`
- `ollama_storage`
- `open_webui`
- `docker-compose.yml`
- `Dockerfile`
- `scripts/server`
