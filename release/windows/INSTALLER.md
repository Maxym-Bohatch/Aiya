# Installer

Use `AiyaInstaller.exe` when you want a single bootstrap installer.

Installer options:
- Client only: installs the ready desktop launcher executable plus the client-side source/scripts.
- Server only: downloads the repo snapshot and installs the Docker/backend side.
- Client + Server: installs the whole repo plus the ready client launcher executable.

For `Server only` and `Client + Server`:
- the installer can check Docker / WSL presence
- the installer can launch Docker Desktop installation through `winget`
- the installed folder also contains `Install Docker For Server.cmd`

The installer downloads the selected GitHub branch as a zip snapshot and writes `INSTALL_INFO.json`.
It also copies `AiyaUninstaller.exe` into the install folder.

# Uninstaller

Use `AiyaUninstaller.exe` from inside the install folder.

Safe defaults:
- remove app files
- keep env files
- keep Docker data folders

Only remove `postgres_data`, `ollama_storage`, and `open_webui` if you are sure you no longer need them.
