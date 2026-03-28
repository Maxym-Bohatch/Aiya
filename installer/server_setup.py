from __future__ import annotations

import os
import secrets
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk


def generate_secret(length: int = 24) -> str:
    return secrets.token_urlsafe(length)[:length]


def desktop_dir() -> Path:
    user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    return user_profile / "Desktop"


class ServerSetupDialog:
    def __init__(self, parent: tk.Tk):
        self.top = tk.Toplevel(parent)
        self.top.title("Server Setup")
        self.top.geometry("760x760")
        self.top.minsize(720, 700)
        self.top.transient(parent)
        self.top.grab_set()

        self.result: dict | None = None

        self.telegram_token_var = tk.StringVar()
        self.db_password_var = tk.StringVar(value=generate_secret())
        self.admin_token_var = tk.StringVar(value=generate_secret())
        self.extra_admin_tokens_var = tk.StringVar()
        self.host_control_token_var = tk.StringVar()
        self.profile_var = tk.StringVar(value="balanced")
        self.hardware_var = tk.StringVar(value="")
        self.llm_mode_var = tk.StringVar(value="bundled_ollama")
        self.external_ollama_url_var = tk.StringVar(value="http://host.docker.internal:11434")
        self.external_api_url_var = tk.StringVar(value="https://api.openai.com/v1")
        self.external_api_key_var = tk.StringVar()
        self.chat_model_var = tk.StringVar(value="qwen2.5:3b")
        self.embed_model_var = tk.StringVar(value="nomic-embed-text")
        self.vision_model_var = tk.StringVar(value="llava:7b")
        self.translation_model_var = tk.StringVar()
        self.enable_tts_var = tk.BooleanVar(value=True)
        self.enable_ocr_var = tk.BooleanVar(value=False)
        self.enable_vision_var = tk.BooleanVar(value=True)
        self.enable_image_var = tk.BooleanVar(value=False)
        self.autostart_server_var = tk.BooleanVar(value=True)

        self._build()
        self.llm_mode_var.trace_add("write", lambda *_: self._sync_llm_mode())
        self._sync_llm_mode()

    def _build(self):
        shell = ttk.Frame(self.top, padding=16)
        shell.pack(fill="both", expand=True)

        ttk.Label(shell, text="Server First-Run Setup", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            shell,
            text="This setup is required before backend installation. The installer will write .env, build Docker, and prepare a desktop launcher.",
            wraplength=700,
        ).pack(anchor="w", pady=(4, 12))

        canvas = tk.Canvas(shell, highlightthickness=0)
        scrollbar = ttk.Scrollbar(shell, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas)
        content.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        required_box = ttk.LabelFrame(content, text="Required Access")
        required_box.pack(fill="x", pady=(0, 10))
        self._entry(required_box, "Telegram token", self.telegram_token_var, 0, show="*")
        self._entry(required_box, "Database password", self.db_password_var, 1, show="*")
        self._entry(required_box, "Admin token", self.admin_token_var, 2, show="*")
        self._entry(required_box, "Extra admin tokens", self.extra_admin_tokens_var, 3)
        self._entry(required_box, "Host control token", self.host_control_token_var, 4, show="*")
        ttk.Button(required_box, text="Regenerate secrets", command=self._regenerate_secrets).grid(row=5, column=1, sticky="w", pady=(6, 10))

        runtime_box = ttk.LabelFrame(content, text="Server Runtime")
        runtime_box.pack(fill="x", pady=(0, 10))
        ttk.Label(runtime_box, text="Performance profile").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Combobox(runtime_box, textvariable=self.profile_var, values=["low", "balanced", "high"], state="readonly", width=24).grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(runtime_box, text="Hardware class (optional)").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Combobox(runtime_box, textvariable=self.hardware_var, values=["", "cpu", "intel", "amd", "nvidia"], state="readonly", width=24).grid(row=1, column=1, sticky="w", pady=6)

        feature_box = ttk.LabelFrame(content, text="Features")
        feature_box.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(feature_box, text="Enable TTS", variable=self.enable_tts_var).pack(anchor="w", padx=12, pady=4)
        ttk.Checkbutton(feature_box, text="Enable OCR", variable=self.enable_ocr_var).pack(anchor="w", padx=12, pady=4)
        ttk.Checkbutton(feature_box, text="Enable Vision", variable=self.enable_vision_var).pack(anchor="w", padx=12, pady=4)
        ttk.Checkbutton(feature_box, text="Enable image generation", variable=self.enable_image_var).pack(anchor="w", padx=12, pady=4)

        llm_box = ttk.LabelFrame(content, text="LLM Source")
        llm_box.pack(fill="x", pady=(0, 10))
        ttk.Radiobutton(llm_box, text="Bundled Ollama in Docker", value="bundled_ollama", variable=self.llm_mode_var).pack(anchor="w", padx=12, pady=4)
        ttk.Radiobutton(llm_box, text="External Ollama server", value="external_ollama", variable=self.llm_mode_var).pack(anchor="w", padx=12, pady=4)
        ttk.Radiobutton(llm_box, text="External OpenAI-compatible API", value="external_api", variable=self.llm_mode_var).pack(anchor="w", padx=12, pady=4)
        ttk.Label(
            llm_box,
            text="You can use bundled Ollama, an external Ollama server, or an OpenAI-compatible API endpoint.",
            wraplength=660,
        ).pack(anchor="w", padx=12, pady=(2, 10))

        self.external_ollama_box = ttk.Frame(llm_box)
        self.external_ollama_box.pack(fill="x", padx=12, pady=(0, 10))
        self._entry(self.external_ollama_box, "External Ollama URL", self.external_ollama_url_var, 0)

        self.external_api_box = ttk.Frame(llm_box)
        self.external_api_box.pack(fill="x", padx=12, pady=(0, 10))
        self._entry(self.external_api_box, "API base URL", self.external_api_url_var, 0)
        self._entry(self.external_api_box, "API key", self.external_api_key_var, 1, show="*")

        models_box = ttk.LabelFrame(content, text="Model Selection")
        models_box.pack(fill="x", pady=(0, 10))
        self._entry(models_box, "Chat model", self.chat_model_var, 0)
        self._entry(models_box, "Embed model", self.embed_model_var, 1)
        self._entry(models_box, "Vision model", self.vision_model_var, 2)
        self._entry(models_box, "Translation model (optional)", self.translation_model_var, 3)

        finish_box = ttk.LabelFrame(content, text="After Install")
        finish_box.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(
            finish_box,
            text="Immediately build and start the server after files are copied",
            variable=self.autostart_server_var,
        ).pack(anchor="w", padx=12, pady=8)

        actions = ttk.Frame(content)
        actions.pack(fill="x", pady=(8, 8))
        ttk.Button(actions, text="Cancel", command=self._cancel).pack(side="right")
        ttk.Button(actions, text="Save and Continue", command=self._submit).pack(side="right", padx=(0, 8))

        self.top.protocol("WM_DELETE_WINDOW", self._cancel)

    def _entry(self, parent, label: str, variable: tk.StringVar, row: int, show: str | None = None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=6)
        ttk.Entry(parent, textvariable=variable, width=54, show=show or "").grid(row=row, column=1, sticky="ew", pady=6)
        parent.columnconfigure(1, weight=1)

    def _regenerate_secrets(self):
        self.db_password_var.set(generate_secret())
        self.admin_token_var.set(generate_secret())
        if not self.host_control_token_var.get().strip():
            self.host_control_token_var.set(generate_secret())

    def _sync_llm_mode(self):
        ollama_state = "normal" if self.llm_mode_var.get() == "external_ollama" else "disabled"
        api_state = "normal" if self.llm_mode_var.get() == "external_api" else "disabled"
        for child in self.external_ollama_box.winfo_children():
            try:
                child.configure(state=ollama_state)
            except tk.TclError:
                pass
        for child in self.external_api_box.winfo_children():
            try:
                child.configure(state=api_state)
            except tk.TclError:
                pass

    def _submit(self):
        telegram_token = self.telegram_token_var.get().strip()
        db_password = self.db_password_var.get().strip()
        admin_token = self.admin_token_var.get().strip()
        llm_mode = self.llm_mode_var.get().strip()
        external_url = self.external_ollama_url_var.get().strip()
        external_api_url = self.external_api_url_var.get().strip()
        external_api_key = self.external_api_key_var.get().strip()

        if not telegram_token:
            messagebox.showerror("Server Setup", "Telegram token is required for the current backend package.")
            return
        if not db_password:
            messagebox.showerror("Server Setup", "Database password is required.")
            return
        if not admin_token:
            messagebox.showerror("Server Setup", "Admin token is required.")
            return
        if llm_mode == "external_ollama" and not external_url:
            messagebox.showerror("Server Setup", "Provide an external Ollama URL or switch back to bundled Ollama.")
            return
        if llm_mode == "external_api" and (not external_api_url or not external_api_key):
            messagebox.showerror("Server Setup", "Provide both API base URL and API key for the external API mode.")
            return

        self.result = {
            "telegram_token": telegram_token,
            "db_password": db_password,
            "admin_token": admin_token,
            "extra_admin_tokens": self.extra_admin_tokens_var.get().strip(),
            "host_control_token": (self.host_control_token_var.get().strip() or admin_token),
            "performance_profile": self.profile_var.get().strip() or "balanced",
            "hardware_class": self.hardware_var.get().strip(),
            "llm_mode": llm_mode,
            "external_ollama_url": external_url,
            "external_api_url": external_api_url,
            "external_api_key": external_api_key,
            "chat_model": self.chat_model_var.get().strip(),
            "embed_model": self.embed_model_var.get().strip(),
            "vision_model": self.vision_model_var.get().strip(),
            "translation_model": self.translation_model_var.get().strip(),
            "enable_tts": self.enable_tts_var.get(),
            "enable_ocr": self.enable_ocr_var.get(),
            "enable_vision": self.enable_vision_var.get(),
            "enable_image_generation": self.enable_image_var.get(),
            "autostart_server": self.autostart_server_var.get(),
        }
        self.top.destroy()

    def _cancel(self):
        self.result = None
        self.top.destroy()

    def show(self) -> dict | None:
        self.top.wait_window()
        return self.result
