# Docker Migration

Safe move procedure:

1. On the old server PC run `docker compose down`.
2. Back up the project folder and persistent data directories:
   - `postgres_data`
   - `ollama_storage`
   - `open_webui`
3. Back up the server env file separately:
   - `.env` or `.env.server`
4. Install Docker Desktop on the new PC before copying data.
5. Restore the project and data on the new PC.
6. Confirm the new PC has enough disk space for Ollama models and database files.
7. Confirm ports are available: `5433`, `8000`, `11434`, `3000`, `3001`, `8765`.
8. Start with `scripts/server/start_server.ps1`.
9. Test:
   - `http://localhost:8000/health`
   - `http://localhost:3000`
   - `http://localhost:3001`
10. Rotate `AIYA_ADMIN_TOKEN` and `HOST_CONTROL_TOKEN` if the old machine is no longer trusted.

Security notes:
- Avoid copying env files through chat apps or screenshots.
- Prefer encrypted storage or encrypted transfer.
- Treat PostgreSQL data and Ollama models as sensitive local state.
