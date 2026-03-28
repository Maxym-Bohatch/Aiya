from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk

import requests

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


def validate_telegram_token(token: str, timeout_seconds: int = 15) -> tuple[bool, str]:
    normalized = (token or "").strip()
    if not normalized:
        return False, "Telegram token is empty."
    try:
        response = requests.get(
            f"https://api.telegram.org/bot{normalized}/getMe",
            timeout=timeout_seconds,
        )
        payload = response.json() if response.headers.get("Content-Type", "").startswith("application/json") else {}
        if response.ok and payload.get("ok"):
            bot_name = payload.get("result", {}).get("username") or payload.get("result", {}).get("first_name") or "unknown bot"
            return True, f"Telegram token is valid ({bot_name})."
        description = payload.get("description") or f"HTTP {response.status_code}"
        return False, f"Telegram rejected the token: {description}"
    except Exception as exc:
        return False, f"Could not verify Telegram token: {exc}"


def bind_entry_clipboard_shortcuts(widget):
    def _paste(_event=None):
        try:
            value = widget.clipboard_get()
        except Exception:
            return "break"
        widget.insert("insert", value)
        return "break"

    widget.bind("<Control-v>", _paste, add="+")
    widget.bind("<Control-V>", _paste, add="+")
    widget.bind("<Shift-Insert>", _paste, add="+")


def enable_mousewheel_scrolling(canvas, root):
    def _scroll(event):
        if event.delta:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        elif getattr(event, "num", None) == 4:
            canvas.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5:
            canvas.yview_scroll(1, "units")

    def _bind(_event=None):
        root.bind_all("<MouseWheel>", _scroll)
        root.bind_all("<Button-4>", _scroll)
        root.bind_all("<Button-5>", _scroll)

    def _unbind(_event=None):
        root.unbind_all("<MouseWheel>")
        root.unbind_all("<Button-4>")
        root.unbind_all("<Button-5>")

    canvas.bind("<Enter>", _bind)
    canvas.bind("<Leave>", _unbind)


def create_scrollable_frame(
    parent,
    root,
    *,
    canvas_bg: str,
    use_ttk_frame: bool = True,
    frame_style: str | None = None,
    frame_bg: str | None = None,
    frame_padding=0,
):
    canvas = tk.Canvas(parent, highlightthickness=0, bg=canvas_bg)
    scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    if use_ttk_frame:
        frame = ttk.Frame(canvas, style=frame_style or "", padding=frame_padding)
    else:
        frame = tk.Frame(canvas, bg=frame_bg or canvas_bg)
    window_id = canvas.create_window((0, 0), window=frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    def _refresh_scrollregion(_event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _sync_width(event):
        canvas.itemconfigure(window_id, width=event.width)

    frame.bind("<Configure>", _refresh_scrollregion)
    canvas.bind("<Configure>", _sync_width)
    enable_mousewheel_scrolling(canvas, root)
    return canvas, frame, scrollbar
