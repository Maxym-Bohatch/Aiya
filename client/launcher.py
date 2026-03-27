from __future__ import annotations

import importlib
import os
import subprocess
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

import requests

from client.env_tools import ensure_defaults, generate_secure_token, parse_env_file, save_env_file
from client.help_content import HELP_TEXT
from client.system_checks import CheckResult, find_tesseract_path, format_check_report, list_tesseract_languages, run_client_checks

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / ".env.client"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / ".env.client.example"
CLIENT_PREREQS_SCRIPT = PROJECT_ROOT / "scripts" / "client" / "install_client_prereqs.ps1"
OCR_LANGS_SCRIPT = PROJECT_ROOT / "scripts" / "client" / "install_tesseract_langs.ps1"
os.environ.setdefault("AIYA_ENV_FILE", str(DEFAULT_CONFIG_PATH))

DEFAULTS = {
    "API_URL": "http://127.0.0.1:8000",
    "OLLAMA_HOST": "http://127.0.0.1:11434",
    "REMOTE_WEB_URL": "http://127.0.0.1:3000",
    "REMOTE_OPEN_WEBUI_URL": "http://127.0.0.1:3001",
    "HOST_CONTROL_URL": "http://127.0.0.1:8765",
    "HOST_CONTROL_TOKEN": "",
    "AIYA_ADMIN_TOKEN": "",
    "AIYA_CLIENT_MODE": "desktop",
    "AIYA_CLIENT_USER_NAME": "DesktopUser",
    "AIYA_CLIENT_EXTERNAL_ID": "900001",
    "AIYA_CLIENT_PLATFORM": "desktop",
    "AIYA_TESSERACT_CMD": "",
    "AIYA_OCR_LANGS": "ukr+eng",
    "AIYA_TRANSLATION_SOURCE_LANG": "auto",
    "AIYA_TRANSLATION_TARGET_LANG": "uk",
    "AIYA_CHARACTER_ASSET": "",
    "AIYA_CHARACTER_DOCK": "right",
    "AIYA_CHARACTER_SCALE": "1.0",
    "AIYA_SUBTITLE_OVERLAY": "true",
    "AIYA_CHARACTER_OVERLAY": "true",
}

FEATURE_FIELDS = [
    ("tts_enabled", "TTS"),
    ("ocr_enabled", "OCR"),
    ("emoji_enabled", "Emoji"),
    ("desktop_subtitles_enabled", "Subtitles"),
    ("image_generation_enabled", "Image Generation"),
]

SERVER_SECRET_FIELDS = [
    ("AIYA_ADMIN_TOKEN", "Admin Token"),
    ("AIYA_EXTRA_ADMIN_TOKENS", "Extra Admin Tokens"),
    ("HOST_CONTROL_TOKEN", "Host Token"),
    ("TELEGRAM_TOKEN", "Telegram Token"),
    ("DB_PASSWORD", "DB Password"),
    ("AIYA_TTS_PROVIDER", "TTS Provider"),
    ("TTS_VOICE", "TTS Voice"),
    ("AIYA_TTS_RATE", "TTS Rate"),
    ("AIYA_TTS_PITCH", "TTS Pitch"),
    ("AIYA_ALLOW_LOCAL_TTS", "Allow Local TTS"),
    ("OLLAMA_CHAT_MODEL", "Chat Model"),
    ("AIYA_TRANSLATION_MODEL", "Translation Model"),
    ("AIYA_TTS_PROVIDER", "TTS Provider"),
    ("TTS_VOICE", "TTS Voice"),
    ("AIYA_TTS_RATE", "TTS Rate"),
    ("AIYA_TTS_PITCH", "TTS Pitch"),
    ("AIYA_ALLOW_LOCAL_TTS", "Allow Local TTS"),
]


class AiyaClientLauncher:
    def __init__(self):
        self.config_path = DEFAULT_CONFIG_PATH
        self.values = self._load_values()
        self.companion = None
        self.latest_checks: list[CheckResult] = []

        self.root = tk.Tk()
        self.root.title("Aiya Client Launcher")
        self.root.geometry("1240x930")
        self.root.minsize(1080, 800)
        self.root.configure(bg="#f4efe6")

        self.status_var = tk.StringVar(value=f"Config: {self.config_path}")
        self.connection_vars = {key: tk.StringVar(value=self.values.get(key, "")) for key in DEFAULTS}
        self.feature_vars = {key: tk.BooleanVar(value=False) for key, _ in FEATURE_FIELDS}
        self.server_config_vars = {key: tk.StringVar() for key, _ in SERVER_SECRET_FIELDS}
        self.wiki_query_var = tk.StringVar()
        self.wiki_lang_var = tk.StringVar(value="uk")

        self._configure_styles()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(300, self.run_client_diagnostics)

    def _configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Aiya.TFrame", background="#f4efe6")
        style.configure("Aiya.TNotebook.Tab", padding=(12, 8), font=("Segoe UI Semibold", 10))
        style.configure("Aiya.TButton", padding=8, font=("Segoe UI Semibold", 10))
        style.configure("Aiya.TLabel", background="#f4efe6", font=("Segoe UI", 10))

    def _load_values(self) -> dict[str, str]:
        base = parse_env_file(EXAMPLE_CONFIG_PATH) if EXAMPLE_CONFIG_PATH.exists() else {}
        current = parse_env_file(self.config_path)
        return ensure_defaults(current, {**DEFAULTS, **base})

    def _build_ui(self):
        shell = ttk.Frame(self.root, style="Aiya.TFrame", padding=16)
        shell.pack(fill="both", expand=True)

        ttk.Label(shell, text="Aiya Desktop Client", style="Aiya.TLabel", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(
            shell,
            text="Launcher, dependency checks, OCR/Tesseract setup, Docker bridge, admin secrets, wiki, and desktop companion.",
            style="Aiya.TLabel",
        ).pack(anchor="w", pady=(4, 10))

        action_bar = ttk.Frame(shell, style="Aiya.TFrame")
        action_bar.pack(fill="x", pady=(0, 10))
        action_buttons = [
            ("Save Config", self.save_config),
            ("Check Client Setup", self.run_client_diagnostics),
            ("Ping API", self.check_api_health),
            ("Ping Host Bridge", self.check_host_bridge),
            ("Install Tesseract", self.install_tesseract),
            ("Install OCR Langs", self.install_ocr_languages),
            ("Install Python Deps", self.install_client_requirements),
            ("Open Companion", self.open_companion),
            ("Close Companion", self.close_companion),
        ]
        for label, command in action_buttons:
            ttk.Button(action_bar, text=label, command=command, style="Aiya.TButton").pack(side="left", padx=(0, 8))

        notebook = ttk.Notebook(shell)
        notebook.pack(fill="both", expand=True)
        self.connection_tab = ttk.Frame(notebook, style="Aiya.TFrame", padding=14)
        self.admin_tab = ttk.Frame(notebook, style="Aiya.TFrame", padding=14)
        self.docker_tab = ttk.Frame(notebook, style="Aiya.TFrame", padding=14)
        self.wiki_tab = ttk.Frame(notebook, style="Aiya.TFrame", padding=14)
        self.help_tab = ttk.Frame(notebook, style="Aiya.TFrame", padding=14)
        notebook.add(self.connection_tab, text="Connection")
        notebook.add(self.admin_tab, text="Admin")
        notebook.add(self.docker_tab, text="Docker")
        notebook.add(self.wiki_tab, text="Wiki")
        notebook.add(self.help_tab, text="Help")

        self._build_connection_tab()
        self._build_admin_tab()
        self._build_docker_tab()
        self._build_wiki_tab()
        self._build_help_tab()

        ttk.Label(shell, textvariable=self.status_var, style="Aiya.TLabel").pack(anchor="w", pady=(10, 0))
        self.log = tk.Text(shell, height=10, wrap="word", bg="#fffdf8", fg="#2a241f", relief="solid", font=("Consolas", 10))
        self.log.pack(fill="both", expand=False, pady=(10, 0))
        self._append_log("Launcher ready.")

    def _make_readonly_text(self, parent, *, height: int, font: tuple[str, int] | tuple[str, int, str] = ("Segoe UI", 10)):
        widget = tk.Text(parent, height=height, wrap="word", bg="#fffdf8", relief="solid", font=font)
        widget.bind("<Key>", self._readonly_keypress)
        widget.bind("<Control-a>", self._select_all_text)
        widget.bind("<Control-A>", self._select_all_text)
        return widget

    def _select_all_text(self, event):
        event.widget.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _readonly_keypress(self, event):
        if event.state & 0x4 and event.keysym.lower() in {"a", "c", "insert"}:
            return None
        if event.keysym in {"Left", "Right", "Up", "Down", "Prior", "Next", "Home", "End"}:
            return None
        return "break"

    def _build_connection_tab(self):
        rows = [
            ("API URL", "API_URL"),
            ("Ollama Host", "OLLAMA_HOST"),
            ("Aiya Web URL", "REMOTE_WEB_URL"),
            ("Open WebUI URL", "REMOTE_OPEN_WEBUI_URL"),
            ("Host Control URL", "HOST_CONTROL_URL"),
            ("Tesseract Path", "AIYA_TESSERACT_CMD"),
            ("OCR Languages", "AIYA_OCR_LANGS"),
            ("Translation From", "AIYA_TRANSLATION_SOURCE_LANG"),
            ("Translation To", "AIYA_TRANSLATION_TARGET_LANG"),
            ("Character Asset", "AIYA_CHARACTER_ASSET"),
            ("Character Dock", "AIYA_CHARACTER_DOCK"),
            ("Character Scale", "AIYA_CHARACTER_SCALE"),
            ("Client Mode", "AIYA_CLIENT_MODE"),
        ]
        for index, (label, key) in enumerate(rows):
            ttk.Label(self.connection_tab, text=label, style="Aiya.TLabel").grid(row=index, column=0, sticky="w", pady=6, padx=(0, 12))
            ttk.Entry(self.connection_tab, textvariable=self.connection_vars[key], width=72).grid(row=index, column=1, sticky="ew", pady=6)
        self.connection_tab.columnconfigure(1, weight=1)

        info = self._make_readonly_text(self.connection_tab, height=7)
        info.grid(row=len(rows), column=0, columnspan=2, sticky="nsew", pady=(14, 10))
        info.insert(
            "1.0",
            "Use localhost when client and server are on the same PC. Use a LAN or Hamachi IP for split deployment.\n\n"
            "Tesseract is used for OCR. Set OCR languages like ukr+eng, and translation languages like auto -> uk.\n\n"
            "Hotkeys in companion: F8 capture, F9 OCR, F10 game, F11 translation area.\n\n"
            "Run 'Check Client Setup' after changing machines so the launcher can spot missing Tesseract or Python dependencies.",
        )

        diag_label = ttk.Label(self.connection_tab, text="Client Diagnostics", style="Aiya.TLabel", font=("Segoe UI Semibold", 11))
        diag_label.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=(2, 6))
        self.diagnostics_output = tk.Text(self.connection_tab, height=12, wrap="word", bg="#fffdf8", relief="solid", font=("Consolas", 10))
        self.diagnostics_output.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="nsew")
        self.diagnostics_output.bind("<Key>", self._readonly_keypress)
        self.diagnostics_output.bind("<Control-a>", self._select_all_text)
        self.diagnostics_output.bind("<Control-A>", self._select_all_text)
        self.connection_tab.rowconfigure(len(rows) + 2, weight=1)

    def _build_admin_tab(self):
        rows = [
            ("Admin Token", "AIYA_ADMIN_TOKEN"),
            ("Host Control Token", "HOST_CONTROL_TOKEN"),
            ("Desktop User Name", "AIYA_CLIENT_USER_NAME"),
            ("Desktop External ID", "AIYA_CLIENT_EXTERNAL_ID"),
            ("Desktop Platform", "AIYA_CLIENT_PLATFORM"),
        ]
        for index, (label, key) in enumerate(rows):
            ttk.Label(self.admin_tab, text=label, style="Aiya.TLabel").grid(row=index, column=0, sticky="w", pady=6, padx=(0, 12))
            show = "*" if "TOKEN" in key else ""
            ttk.Entry(self.admin_tab, textvariable=self.connection_vars[key], width=72, show=show).grid(row=index, column=1, sticky="ew", pady=6)
        self.admin_tab.columnconfigure(1, weight=1)

        actions = ttk.Frame(self.admin_tab, style="Aiya.TFrame")
        actions.grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(10, 10))
        ttk.Button(actions, text="Generate Admin Token", command=self.generate_admin_token, style="Aiya.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Generate Host Token", command=self.generate_host_token, style="Aiya.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Load Desktop Features", command=self.load_desktop_features, style="Aiya.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Apply Desktop Features", command=self.apply_desktop_features, style="Aiya.TButton").pack(side="left")

        feature_box = ttk.LabelFrame(self.admin_tab, text="Desktop Feature Flags")
        feature_box.grid(row=len(rows) + 1, column=0, columnspan=2, sticky="ew")
        for index, (key, label) in enumerate(FEATURE_FIELDS):
            ttk.Checkbutton(feature_box, text=label, variable=self.feature_vars[key]).grid(row=index // 3, column=index % 3, sticky="w", padx=10, pady=8)

        server_box = ttk.LabelFrame(self.admin_tab, text="Server Secrets And Tokens")
        server_box.grid(row=len(rows) + 2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        for index, (key, label) in enumerate(SERVER_SECRET_FIELDS):
            ttk.Label(server_box, text=label).grid(row=index, column=0, sticky="w", padx=(10, 8), pady=6)
            show = "*" if "TOKEN" in key or "PASSWORD" in key else ""
            ttk.Entry(server_box, textvariable=self.server_config_vars[key], width=60, show=show).grid(row=index, column=1, sticky="ew", padx=(0, 10), pady=6)
        server_box.columnconfigure(1, weight=1)
        server_actions = ttk.Frame(server_box, style="Aiya.TFrame")
        server_actions.grid(row=len(SERVER_SECRET_FIELDS), column=0, columnspan=2, sticky="w", padx=10, pady=(4, 10))
        ttk.Button(server_actions, text="Load Server Config", command=self.load_server_config, style="Aiya.TButton").pack(side="left", padx=(0, 8))
        ttk.Button(server_actions, text="Apply Server Config", command=self.apply_server_config, style="Aiya.TButton").pack(side="left")

        notes = self._make_readonly_text(self.admin_tab, height=7)
        notes.grid(row=len(rows) + 3, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        notes.insert(
            "1.0",
            "Host bridge can rotate admin and host tokens, Telegram token, extra admin tokens, and DB password from the client side.\n\n"
            "Extra admins are stored as a comma-separated token list in AIYA_EXTRA_ADMIN_TOKENS.\n\n"
            "DB password rotation is applied on the running PostgreSQL instance before the .env file is rewritten.",
        )
        self.admin_tab.rowconfigure(len(rows) + 3, weight=1)

    def _build_docker_tab(self):
        ttk.Label(self.docker_tab, text="Use the host bridge to manage Docker services and inspect host capabilities.", style="Aiya.TLabel").pack(anchor="w", pady=(0, 10))
        buttons = ttk.Frame(self.docker_tab, style="Aiya.TFrame")
        buttons.pack(fill="x")
        actions = [
            ("Check Host Bridge", self.check_host_bridge),
            ("Start API", lambda: self.start_service("api")),
            ("Start Telegram", lambda: self.start_service("telegram")),
            ("Start Web", lambda: self.start_service("web")),
        ]
        for label, command in actions:
            ttk.Button(buttons, text=label, command=command, style="Aiya.TButton").pack(side="left", padx=(0, 8))
        self.docker_output = tk.Text(self.docker_tab, wrap="word", bg="#fffdf8", relief="solid", font=("Consolas", 10))
        self.docker_output.pack(fill="both", expand=True, pady=(12, 0))
        self.docker_output.bind("<Key>", self._readonly_keypress)
        self.docker_output.bind("<Control-a>", self._select_all_text)
        self.docker_output.bind("<Control-A>", self._select_all_text)

    def _build_wiki_tab(self):
        search_row = ttk.Frame(self.wiki_tab, style="Aiya.TFrame")
        search_row.pack(fill="x")
        ttk.Label(search_row, text="Query", style="Aiya.TLabel").pack(side="left")
        ttk.Entry(search_row, textvariable=self.wiki_query_var, width=56).pack(side="left", padx=(8, 8))
        ttk.Label(search_row, text="Lang", style="Aiya.TLabel").pack(side="left")
        ttk.Entry(search_row, textvariable=self.wiki_lang_var, width=8).pack(side="left", padx=(8, 8))
        ttk.Button(search_row, text="Search Wiki", command=self.search_wiki, style="Aiya.TButton").pack(side="left")
        self.wiki_output = tk.Text(self.wiki_tab, wrap="word", bg="#fffdf8", relief="solid", font=("Segoe UI", 10))
        self.wiki_output.pack(fill="both", expand=True, pady=(12, 0))
        self.wiki_output.bind("<Key>", self._readonly_keypress)
        self.wiki_output.bind("<Control-a>", self._select_all_text)
        self.wiki_output.bind("<Control-A>", self._select_all_text)

    def _build_help_tab(self):
        help_box = tk.Text(self.help_tab, wrap="word", bg="#fffdf8", relief="solid", font=("Segoe UI", 10))
        help_box.pack(fill="both", expand=True)
        help_box.insert("1.0", HELP_TEXT)
        help_box.bind("<Key>", self._readonly_keypress)
        help_box.bind("<Control-a>", self._select_all_text)
        help_box.bind("<Control-A>", self._select_all_text)

    def _append_log(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.status_var.set(text)

    def _set_output_widget(self, widget: tk.Text, text: str):
        widget.delete("1.0", "end")
        widget.insert("1.0", text)

    def _set_diagnostics_output(self, text: str):
        self._set_output_widget(self.diagnostics_output, text)

    def _set_docker_output(self, text: str):
        self._set_output_widget(self.docker_output, text)

    def _set_wiki_output(self, text: str):
        self._set_output_widget(self.wiki_output, text)

    def _run_background(self, action: Callable[[], None]):
        threading.Thread(target=action, daemon=True).start()

    def save_config(self):
        if not self.connection_vars["AIYA_TESSERACT_CMD"].get().strip():
            detected = find_tesseract_path()
            if detected:
                self.connection_vars["AIYA_TESSERACT_CMD"].set(str(detected))
        values = {key: var.get().strip() for key, var in self.connection_vars.items()}
        save_env_file(self.config_path, ensure_defaults(values, DEFAULTS))
        for key, value in values.items():
            os.environ[key] = value
        os.environ["AIYA_ENV_FILE"] = str(self.config_path)
        self._append_log(f"Saved client config to {self.config_path}")

    def run_client_diagnostics(self):
        values = {key: var.get().strip() for key, var in self.connection_vars.items()}
        self.latest_checks = run_client_checks(values)
        detected = find_tesseract_path(values.get("AIYA_TESSERACT_CMD", ""))
        if detected and not values.get("AIYA_TESSERACT_CMD", "").strip():
            self.connection_vars["AIYA_TESSERACT_CMD"].set(str(detected))
        report = format_check_report(self.latest_checks)
        languages = list_tesseract_languages(values.get("AIYA_TESSERACT_CMD", ""))
        if languages:
            report += "\n\nDetected OCR languages:\n" + "\n".join(f"- {lang}" for lang in languages)
        self._set_diagnostics_output(report)
        missing_required = [check.name for check in self.latest_checks if not check.ok and not check.optional]
        if missing_required:
            self._append_log(f"Client setup needs attention: {', '.join(missing_required)}")
        else:
            self._append_log("Client setup looks healthy.")

    def install_client_requirements(self):
        if not CLIENT_PREREQS_SCRIPT.exists():
            self._append_log("Client prerequisite installer script is missing.")
            return
        self._append_log("Starting the client prerequisite installer. A PowerShell window may ask for confirmation.")
        try:
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(CLIENT_PREREQS_SCRIPT),
                ],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            self._append_log(f"Failed to launch client prerequisite installer: {exc}")

    def generate_admin_token(self):
        self.connection_vars["AIYA_ADMIN_TOKEN"].set(generate_secure_token())
        self._append_log("Generated a new admin token locally. Save config to persist it.")

    def generate_host_token(self):
        self.connection_vars["HOST_CONTROL_TOKEN"].set(generate_secure_token())
        self._append_log("Generated a new host control token locally. Save config to persist it.")

    def _api_url(self, suffix: str) -> str:
        return self.connection_vars["API_URL"].get().rstrip("/") + suffix

    def _host_url(self, suffix: str) -> str:
        return self.connection_vars["HOST_CONTROL_URL"].get().rstrip("/") + suffix

    def _host_headers(self) -> dict[str, str]:
        token = self.connection_vars["HOST_CONTROL_TOKEN"].get().strip()
        return {"X-Aiya-Host-Token": token} if token else {}

    def check_api_health(self):
        def action():
            try:
                response = requests.get(self._api_url("/health"), timeout=10)
                response.raise_for_status()
                payload = response.json()
                self.root.after(0, lambda: self._append_log(f"API OK: profile={payload.get('performance')} features={payload.get('features')}"))
            except Exception as exc:
                self.root.after(0, lambda: self._append_log(f"API health failed: {exc}"))
        self._run_background(action)

    def check_host_bridge(self):
        def action():
            try:
                response = requests.get(self._host_url("/capabilities"), headers=self._host_headers(), timeout=12)
                response.raise_for_status()
                payload = response.json()
                text = (
                    f"Host bridge OK\n\nproject_dir: {payload.get('project_dir')}\n"
                    f"docker_cli: {payload.get('docker_cli')}\n"
                    f"nvidia_smi: {payload.get('nvidia_smi')}\n"
                    f"winget: {payload.get('winget')}\n"
                    f"supported_services: {payload.get('supported_services')}\n\n"
                    f"compose_status:\n{payload.get('compose_status', '')}"
                )
                self.root.after(0, lambda: self._set_docker_output(text))
                self.root.after(0, lambda: self._append_log("Host bridge responded successfully."))
            except Exception as exc:
                self.root.after(0, lambda: self._set_docker_output(f"Host bridge error: {exc}"))
                self.root.after(0, lambda: self._append_log(f"Host bridge check failed: {exc}"))
        self._run_background(action)

    def start_service(self, service_name: str):
        def action():
            try:
                response = requests.post(self._host_url(f"/services/{service_name}/start"), headers=self._host_headers(), timeout=60)
                response.raise_for_status()
                payload = response.json()
                self.root.after(0, lambda: self._set_docker_output(f"Service {service_name}:\n\n{payload.get('message', 'ok')}"))
                self.root.after(0, lambda: self._append_log(f"Requested start for {service_name}."))
            except Exception as exc:
                self.root.after(0, lambda: self._set_docker_output(f"Start {service_name} failed: {exc}"))
                self.root.after(0, lambda: self._append_log(f"Service start failed for {service_name}: {exc}"))
        self._run_background(action)

    def install_tesseract(self):
        self._append_log("Starting Tesseract install via winget. Windows may ask for elevation.")
        try:
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    "Start-Process winget -Verb RunAs -ArgumentList 'install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements'",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            self._append_log(f"Failed to launch Tesseract install: {exc}")

    def install_ocr_languages(self):
        if not OCR_LANGS_SCRIPT.exists():
            self._append_log("OCR language installer script is missing.")
            return
        langs = self.connection_vars["AIYA_OCR_LANGS"].get().strip() or "ukr+eng"
        self._append_log(f"Installing OCR language packs for: {langs}")
        try:
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(OCR_LANGS_SCRIPT),
                    "-Langs",
                    langs,
                ],
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            self._append_log(f"Failed to launch OCR language installer: {exc}")

    def load_desktop_features(self):
        def action():
            try:
                response = requests.get(
                    self._api_url(
                        f"/users/{self.connection_vars['AIYA_CLIENT_PLATFORM'].get().strip()}/{self.connection_vars['AIYA_CLIENT_EXTERNAL_ID'].get().strip()}/features"
                    ),
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json()

                def apply_payload():
                    for key, _label in FEATURE_FIELDS:
                        self.feature_vars[key].set(bool(payload.get(key, False)))
                    self._append_log("Loaded desktop user feature flags from API.")

                self.root.after(0, apply_payload)
            except Exception as exc:
                self.root.after(0, lambda: self._append_log(f"Loading features failed: {exc}"))
        self._run_background(action)

    def apply_desktop_features(self):
        def action():
            try:
                response = requests.patch(
                    self._api_url(
                        f"/users/{self.connection_vars['AIYA_CLIENT_PLATFORM'].get().strip()}/{self.connection_vars['AIYA_CLIENT_EXTERNAL_ID'].get().strip()}/features"
                    ),
                    json={key: var.get() for key, var in self.feature_vars.items()},
                    timeout=20,
                )
                response.raise_for_status()
                self.root.after(0, lambda: self._append_log("Applied desktop user feature flags."))
            except Exception as exc:
                self.root.after(0, lambda: self._append_log(f"Applying features failed: {exc}"))
        self._run_background(action)

    def load_server_config(self):
        def action():
            try:
                response = requests.get(self._host_url("/config"), headers=self._host_headers(), timeout=20)
                response.raise_for_status()
                payload = response.json().get("config", {})

                def apply_values():
                    for key, var in self.server_config_vars.items():
                        var.set(payload.get(key, ""))
                    self._append_log("Loaded server config through host bridge.")

                self.root.after(0, apply_values)
            except Exception as exc:
                self.root.after(0, lambda: self._append_log(f"Loading server config failed: {exc}"))
        self._run_background(action)

    def apply_server_config(self):
        def action():
            updates = {key: var.get().strip() for key, var in self.server_config_vars.items() if var.get().strip()}
            try:
                response = requests.post(
                    self._host_url("/config/update"),
                    headers=self._host_headers(),
                    json={"updates": updates, "restart_services": True},
                    timeout=60,
                )
                response.raise_for_status()
                payload = response.json()
                changed = ", ".join(payload.get("changed_keys", [])) or "no changes"
                restart_message = payload.get("restart", {}).get("message", "")
                self.root.after(0, lambda: self._append_log(f"Applied server config: {changed}. {restart_message}"))
            except Exception as exc:
                self.root.after(0, lambda: self._append_log(f"Applying server config failed: {exc}"))
        self._run_background(action)

    def search_wiki(self):
        query = self.wiki_query_var.get().strip()
        if not query:
            messagebox.showinfo("Wiki", "Enter a query first.")
            return

        def action():
            try:
                response = requests.post(
                    self._api_url("/wiki/search"),
                    json={"query": query, "language": self.wiki_lang_var.get().strip() or "uk", "limit": 3},
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
                items = payload.get("items", [])
                if not items:
                    text = payload.get("message", "No results.")
                else:
                    text = "\n\n".join(
                        f"{item.get('title', '')}\n{item.get('description', '')}\n{item.get('extract', '')}\n{item.get('url', '')}"
                        for item in items
                    )
                self.root.after(0, lambda: self._set_wiki_output(text))
                self.root.after(0, lambda: self._append_log(f"Wiki search completed for '{query}'."))
            except Exception as exc:
                self.root.after(0, lambda: self._set_wiki_output(f"Wiki search failed: {exc}"))
                self.root.after(0, lambda: self._append_log(f"Wiki search failed: {exc}"))

        self._run_background(action)

    def open_url(self, url: str):
        target = (url or "").strip()
        if not target:
            messagebox.showinfo("Open URL", "URL is empty.")
            return
        webbrowser.open(target)
        self._append_log(f"Opened {target}")

    def open_companion(self):
        self.save_config()
        self.run_client_diagnostics()
        blocking = [check for check in self.latest_checks if not check.ok and not check.optional and check.name in {"Python requests", "Pillow"}]
        if blocking:
            messagebox.showerror(
                "Companion",
                "The client is missing required Python dependencies.\n\n"
                "Run 'Install Python Deps' and then try again.",
            )
            return

        tesseract_ok = any(check.name == "Tesseract OCR" and check.ok for check in self.latest_checks)
        if not tesseract_ok:
            messagebox.showwarning(
                "Companion",
                "Tesseract was not found. The companion can still open, but OCR and screen text translation will not work until it is installed.",
            )

        if self.companion and getattr(self.companion, "root", None) and self.companion.root.winfo_exists():
            self.companion.root.lift()
            self._append_log("Desktop companion window is already open.")
            return
        try:
            import config
            import desktop_companion

            importlib.reload(config)
            desktop_companion = importlib.reload(desktop_companion)
            self.companion = desktop_companion.AiyaDesktop(master=self.root)
            self._append_log("Opened desktop companion window.")
        except Exception as exc:
            messagebox.showerror("Companion", str(exc))
            self._append_log(f"Opening companion failed: {exc}")

    def close_companion(self):
        if self.companion and getattr(self.companion, "root", None) and self.companion.root.winfo_exists():
            self.companion.root.destroy()
            self.companion = None
            self._append_log("Closed desktop companion window.")
            return
        self._append_log("Desktop companion window is not open.")

    def _on_close(self):
        self.close_companion()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    AiyaClientLauncher().run()
