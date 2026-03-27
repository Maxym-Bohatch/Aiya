HELP_TEXT = """AIYA CLIENT QUICK GUIDE

1. Connection
- API URL: address of the Aiya backend, for example http://127.0.0.1:8000 or http://192.168.0.10:8000
- Remote Web URL: browser address for the Aiya UI
- Remote Open WebUI URL: optional second browser UI
- Host Control URL: host bridge for Docker control, for example http://127.0.0.1:8765 or http://192.168.0.10:8765
- Host Control Token: token required by the host bridge
- Tesseract Path: local path to tesseract.exe on the client PC

2. What this client does
- starts the desktop companion window
- stores client-side configuration in .env.client
- checks client dependencies and can suggest fixes on startup
- checks API and Docker bridge availability
- can request start of API / Telegram / Web services through the host bridge
- can update desktop user feature toggles on the backend
- can query the wiki module from the Docker/backend side

3. Client-only PC layout
- copy only the packaged client bundle to the client PC
- configure .env.client inside that bundle
- do not copy postgres_data, ollama_storage, Dockerfile, docker-compose.yml, or server rebuild scripts to the client PC

4. Server / Docker rebuild
- run scripts/server/start_server.ps1 to start the server side
- run scripts/server/rebuild_docker.ps1 when you intentionally want to rebuild containers
- keep Docker, Ollama data, PostgreSQL data, and server .env only on the server PC

5. Safe Docker move to another PC
- stop the stack cleanly: docker compose down
- copy the project plus persistent data directories: postgres_data, ollama_storage, open_webui
- copy the server env file separately and securely
- install Docker Desktop on the new PC first
- verify ports 5433, 8000, 11434, 3000, 3001 are free or adjust config before start
- on the new PC start with scripts/server/start_server.ps1
- rotate AIYA_ADMIN_TOKEN and HOST_CONTROL_TOKEN if the old machine is no longer trusted
- if you move over a network, use an encrypted channel and avoid sending plain tokens in chat or screenshots

6. Notes
- OCR requires Tesseract installed on the client PC; set AIYA_TESSERACT_CMD if it is not in PATH
- if you run from source, use the launcher's "Install Python Deps" button or scripts/client/install_client_prereqs.ps1
- gamepad mode requires ViGEm / vgamepad support on the client PC
- wiki module works on the backend side and needs outbound internet from the server side if you use public Wikipedia
"""
