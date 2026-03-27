from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

INSTALL_INFO_NAME = "INSTALL_INFO.json"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", app_dir()))
    return base.joinpath(*parts)


def write_install_info(target_dir: Path, payload: dict):
    target_dir.joinpath(INSTALL_INFO_NAME).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_install_info(target_dir: Path) -> dict:
    path = target_dir.joinpath(INSTALL_INFO_NAME)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def remove_path(path: Path):
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def schedule_self_delete(exe_path: Path, target_dir: Path | None = None):
    script_path = exe_path.with_suffix(".cleanup.cmd")
    commands = [
        "@echo off",
        "ping 127.0.0.1 -n 3 >nul",
        f'del /f /q "{exe_path}"',
    ]
    if target_dir:
        commands.append(f'rmdir /s /q "{target_dir}"')
    commands.append(f'del /f /q "{script_path}"')
    script_path.write_text("\r\n".join(commands), encoding="utf-8")
    os.startfile(str(script_path))
