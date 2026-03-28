from __future__ import annotations

import io
import shutil
import tempfile
import zipfile
from datetime import datetime, UTC
from pathlib import Path

import requests

from installer.common import read_install_info, write_install_info

EXCLUDED_ROOT_NAMES = {".git", "__pycache__", "dist", "build"}
PRESERVE_NAMES = {
    ".env",
    ".env.client",
    ".env.server",
    "postgres_data",
    "ollama_storage",
    "open_webui",
    "INSTALL_INFO.json",
}
DEFAULT_REPO_URL = "https://github.com/Maxym-Bohatch/Aiya"
DEFAULT_BRANCH = "main"


def _download_repo(repo_url: str, branch: str) -> Path:
    zip_url = f"{repo_url.rstrip('/')}/archive/refs/heads/{branch}.zip"
    response = requests.get(zip_url, timeout=180)
    response.raise_for_status()
    temp_dir = Path(tempfile.mkdtemp(prefix="aiya-update-"))
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(temp_dir)
    extracted = [path for path in temp_dir.iterdir() if path.is_dir()]
    if not extracted:
        raise RuntimeError("Downloaded archive did not contain a project folder.")
    return extracted[0]


def update_installation(target_dir: Path) -> dict:
    install_dir = Path(target_dir).expanduser().resolve()
    info = read_install_info(install_dir)
    repo_url = info.get("repo_url") or DEFAULT_REPO_URL
    branch = info.get("branch") or DEFAULT_BRANCH
    extracted_root = _download_repo(repo_url, branch)

    for item in extracted_root.iterdir():
        if item.name in EXCLUDED_ROOT_NAMES:
            continue
        if item.name in PRESERVE_NAMES and (install_dir / item.name).exists():
            continue
        destination = install_dir / item.name
        if item.is_dir():
            if destination.exists():
                shutil.rmtree(destination)
            shutil.copytree(item, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)

    info.update(
        {
            "repo_url": repo_url,
            "branch": branch,
            "updated_at_utc": datetime.now(UTC).isoformat(),
        }
    )
    write_install_info(install_dir, info)
    return {
        "ok": True,
        "repo_url": repo_url,
        "branch": branch,
        "updated_at_utc": info["updated_at_utc"],
        "target_dir": str(install_dir),
    }
