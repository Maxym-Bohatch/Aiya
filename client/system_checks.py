from __future__ import annotations

import importlib.util
import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path


COMMON_TESSERACT_PATHS = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    summary: str
    details: str = ""
    optional: bool = False


def find_tesseract_path(configured_path: str = "") -> Path | None:
    configured = Path(configured_path).expanduser() if configured_path else None
    if configured and configured.exists():
        return configured

    from_path = shutil.which("tesseract")
    if from_path:
        return Path(from_path)

    for candidate in COMMON_TESSERACT_PATHS:
        if candidate.exists():
            return candidate
    return None


def _module_present(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def list_tesseract_languages(configured_path: str = "") -> list[str]:
    executable = find_tesseract_path(configured_path)
    if executable is None:
        return []
    try:
        completed = subprocess.run(
            [str(executable), "--list-langs"],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        lines = [line.strip() for line in completed.stdout.splitlines()]
        return [line for line in lines if line and "languages" not in line.lower()]
    except Exception:
        return []


def run_client_checks(values: dict[str, str]) -> list[CheckResult]:
    configured_tesseract = values.get("AIYA_TESSERACT_CMD", "")
    tesseract_path = find_tesseract_path(configured_tesseract)
    edge_ok = _module_present("edge_tts")

    results = [
        CheckResult(
            name="Python requests",
            ok=_module_present("requests"),
            summary="HTTP client module is available." if _module_present("requests") else "Python package 'requests' is missing.",
            details="Run the client dependency installer if you launch from source instead of the packaged EXE.",
        ),
        CheckResult(
            name="Pillow",
            ok=_module_present("PIL"),
            summary="Pillow is available for screen capture." if _module_present("PIL") else "Pillow is missing, so screenshots and OCR previews will fail.",
            details="Install client Python dependencies before launching the companion from source.",
        ),
        CheckResult(
            name="pytesseract",
            ok=_module_present("pytesseract"),
            summary="pytesseract is available." if _module_present("pytesseract") else "pytesseract is missing, so OCR cannot run.",
            details="The packaged EXE should include it, but source mode needs Python dependencies installed.",
        ),
        CheckResult(
            name="edge-tts",
            ok=edge_ok,
            summary="edge-tts is available for the recommended neural voice path." if edge_ok else "edge-tts is missing, so the recommended neural TTS path will be unavailable.",
            details="Install client/server Python dependencies or use a separate TTS_BACKEND_URL.",
            optional=True,
        ),
        CheckResult(
            name="Tesseract OCR",
            ok=tesseract_path is not None,
            summary=f"Tesseract detected at {tesseract_path}" if tesseract_path else "Tesseract executable was not found.",
            details="Install UB Mannheim Tesseract on the client PC or point AIYA_TESSERACT_CMD to tesseract.exe.",
        ),
        CheckResult(
            name="ViGEm / vgamepad",
            ok=_module_present("vgamepad"),
            summary="vgamepad is available for virtual controller mode." if _module_present("vgamepad") else "vgamepad is not installed.",
            details="Optional. Only needed for virtual gamepad control.",
            optional=True,
        ),
        CheckResult(
            name="edge-tts",
            ok=_module_present("edge_tts"),
            summary="edge-tts is available for better voice replies." if _module_present("edge_tts") else "edge-tts is not installed in this Python environment.",
            details="Optional for source mode, but recommended if you want local client-side TTS diagnostics to match the server setup.",
            optional=True,
        ),
        CheckResult(
            name="winget",
            ok=shutil.which("winget") is not None,
            summary="winget is available for guided installs." if shutil.which("winget") else "winget is not available on this PC.",
            details="Optional, but it makes guided Tesseract installs much easier.",
            optional=True,
        ),
    ]
    return results


def format_check_report(results: list[CheckResult]) -> str:
    lines: list[str] = []
    for result in results:
        prefix = "OK" if result.ok else ("WARN" if result.optional else "NEEDS ACTION")
        lines.append(f"[{prefix}] {result.name}: {result.summary}")
        if result.details:
            lines.append(f"    {result.details}")
    return "\n".join(lines)
