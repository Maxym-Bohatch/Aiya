from __future__ import annotations

import os
import shutil
import subprocess
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from installer.common import create_scrollable_frame
from installer.server_env import read_server_env, write_server_env
from installer.server_setup import ServerSetupDialog
from installer.update_manager import update_installation

PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = PROJECT_ROOT / ".env"
DOCKER_DOC_URL = "https://docs.docker.com/desktop/setup/install/windows-install/"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class AiyaServerLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Aiya Server Launcher")
        self.root.geometry("1120x860")
        self.root.minsize(980, 760)
        self.root.configure(bg="#f4efe6")

        self.status_var = tk.StringVar(value="Ready")
        self.env_var = tk.StringVar(value=self._env_status_text())
        self.health_var = tk.StringVar(value="Server health: unknown")
        self._running = False

        self._configure_styles()
        self._build_ui()
        self.root.after(250, self.refresh_status)

    def _configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Aiya.TFrame", background="#f4efe6")
        style.configure("Aiya.TButton", padding=8, font=("Segoe UI Semibold", 10))
        style.configure("Aiya.TLabel", background="#f4efe6", font=("Segoe UI", 10))

    def _build_ui(self):
        canvas, shell, scrollbar = create_scrollable_frame(
            self.root,
            self.root,
            canvas_bg="#f4efe6",
            frame_style="Aiya.TFrame",
            frame_padding=16,
        )
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        ttk.Label(shell, text="Aiya Server Launcher", style="Aiya.TLabel", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(
            shell,
            text="First-run .env setup, Docker Desktop checks, and one-click server start without using the console.",
            style="Aiya.TLabel",
        ).pack(anchor="w", pady=(4, 12))

        action_bar = ttk.Frame(shell, style="Aiya.TFrame")
        action_bar.pack(fill="x", pady=(0, 10))
        actions = [
            ("Configure .env", self.configure_env),
            ("Start Server", self.start_server),
            ("Stop Server", self.stop_server),
            ("Rebuild Docker", self.rebuild_server),
            ("Update Aiya", self.update_installation_files),
            ("Check Docker", self.check_docker),
            ("Install Docker Desktop", self.install_docker_desktop),
            ("Open Docker Desktop", self.open_docker_desktop),
            ("Open Project Folder", self.open_project_folder),
            ("Open Web UI", lambda: self.open_url("http://localhost:3000")),
            ("Open API Health", lambda: self.open_url("http://localhost:8000/health")),
        ]
        for label, command in actions:
            ttk.Button(action_bar, text=label, command=command, style="Aiya.TButton").pack(side="left", padx=(0, 8), pady=(0, 6))

        status_box = ttk.LabelFrame(shell, text="Status")
        status_box.pack(fill="x", pady=(0, 10))
        ttk.Label(status_box, textvariable=self.env_var, style="Aiya.TLabel").pack(anchor="w", padx=12, pady=(10, 4))
        ttk.Label(status_box, textvariable=self.health_var, style="Aiya.TLabel").pack(anchor="w", padx=12, pady=(0, 10))

        help_box = tk.Text(shell, height=6, wrap="word", bg="#fffdf8", relief="solid", font=("Segoe UI", 10))
        help_box.pack(fill="x", pady=(0, 10))
        help_box.insert(
            "1.0",
            "Recommended flow:\n"
            "1. Click Configure .env on the first run and fill the required tokens.\n"
            "2. Click Install Docker Desktop only if Docker is missing.\n"
            "3. Click Start Server to launch Docker Desktop, build containers, and wait for the local API.\n\n"
            "If you prefer Docker Desktop directly, make sure .env already exists in this folder, then open this project in Docker Desktop and press Play on the compose stack.",
        )
        help_box.configure(state="disabled")

        ttk.Label(shell, textvariable=self.status_var, style="Aiya.TLabel").pack(anchor="w", pady=(0, 6))
        self.log = tk.Text(shell, wrap="word", bg="#fffdf8", fg="#2a241f", relief="solid", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True)
        self._append_log("Server launcher ready.")

    def _set_status(self, text: str):
        self.root.after(0, lambda: self.status_var.set(text))

    def _append_log(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.status_var.set(text)

    def _append_log_async(self, text: str):
        self.root.after(0, lambda: self._append_log(text))

    def _env_status_text(self) -> str:
        return f".env: {'configured' if ENV_PATH.exists() else 'missing'} ({ENV_PATH})"

    def refresh_status(self):
        self.env_var.set(self._env_status_text())
        health_text = "Server health: unavailable"
        if self._command_exists("docker"):
            try:
                completed = subprocess.run(
                    ["docker", "ps", "--format", "{{.Names}}"],
                    cwd=PROJECT_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                names = {line.strip() for line in completed.stdout.splitlines() if line.strip()}
                if "aiya_core" in names:
                    health_text = "Server health: containers are running"
                elif completed.returncode == 0:
                    health_text = "Server health: docker is ready, Aiya containers are not running"
            except Exception:
                health_text = "Server health: docker detected, engine check failed"
        self.health_var.set(health_text)
        self.root.after(5000, self.refresh_status)

    def _command_exists(self, name: str) -> bool:
        return shutil.which(name) is not None

    def _docker_desktop_path(self) -> Path | None:
        candidates = [
            Path(os.environ.get("ProgramFiles", "")) / "Docker/Docker/Docker Desktop.exe",
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Docker/Docker/Docker Desktop.exe",
            Path(os.environ.get("LocalAppData", "")) / "Programs/Docker/Docker/Docker Desktop.exe",
        ]
        for candidate in candidates:
            if str(candidate) and candidate.exists():
                return candidate
        return None

    def open_url(self, url: str):
        webbrowser.open(url)

    def open_project_folder(self):
        os.startfile(str(PROJECT_ROOT))

    def open_docker_desktop(self):
        docker_desktop = self._docker_desktop_path()
        if not docker_desktop:
            messagebox.showwarning("Aiya Server Launcher", "Docker Desktop executable was not found on this PC.")
            return
        os.startfile(str(docker_desktop))
        self._append_log("Opened Docker Desktop.")

    def install_docker_desktop(self):
        if not self._command_exists("winget"):
            self._append_log("winget is missing. Opening Docker Desktop install docs instead.")
            self.open_url(DOCKER_DOC_URL)
            return
        try:
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    "Start-Process winget -Verb RunAs -ArgumentList 'install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements'",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
            self._append_log("Started Docker Desktop installation via winget.")
        except Exception as exc:
            self._append_log(f"Could not start Docker Desktop installation: {exc}")

    def configure_env(self):
        self._open_env_setup(force_rewrite=True)

    def _open_env_setup(self, force_rewrite: bool) -> bool:
        if ENV_PATH.exists() and not force_rewrite:
            return True
        if ENV_PATH.exists() and force_rewrite:
            proceed = messagebox.askyesno(
                "Aiya Server Launcher",
                ".env already exists. Rewrite it using the setup dialog?",
            )
            if not proceed:
                return True
        setup = ServerSetupDialog(self.root, existing_values=read_server_env(PROJECT_ROOT)).show()
        if setup is None:
            self._append_log("Server setup was cancelled.")
            return False
        write_server_env(PROJECT_ROOT, setup)
        self.env_var.set(self._env_status_text())
        self._append_log("Saved server .env.")
        return True

    def _ensure_env(self) -> bool:
        if ENV_PATH.exists():
            return True
        messagebox.showinfo(
            "Aiya Server Launcher",
            "Server .env is missing. Fill the first-run setup before starting Docker.",
        )
        return self._open_env_setup(force_rewrite=False)

    def _start_background(self, title: str, command: list[str]):
        if self._running:
            self._append_log("Another launcher task is already running. Wait for it to finish first.")
            return

        def worker():
            self._running = True
            self._set_status(title)
            self._append_log_async(f"Running: {' '.join(command)}")
            try:
                process = subprocess.Popen(
                    command,
                    cwd=PROJECT_ROOT,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=CREATE_NO_WINDOW,
                )
                assert process.stdout is not None
                for line in process.stdout:
                    text = line.rstrip()
                    if text:
                        self._append_log_async(text)
                code = process.wait()
                if code == 0:
                    self._append_log_async(f"{title} finished successfully.")
                else:
                    self._append_log_async(f"{title} failed with exit code {code}.")
            except Exception as exc:
                self._append_log_async(f"{title} failed: {exc}")
            finally:
                self._running = False
                self._set_status("Ready")

        threading.Thread(target=worker, daemon=True).start()

    def start_server(self):
        if not self._ensure_env():
            return
        self._start_background(
            "Starting Aiya server",
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PROJECT_ROOT / "start_aiya.ps1")],
        )

    def stop_server(self):
        self._start_background(
            "Stopping Aiya server",
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PROJECT_ROOT / "stop_aiya.ps1")],
        )

    def rebuild_server(self):
        if not self._ensure_env():
            return
        self._start_background(
            "Rebuilding Aiya docker stack",
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PROJECT_ROOT / "scripts/server/rebuild_docker.ps1")],
        )

    def update_installation_files(self):
        if self._running:
            self._append_log("Another launcher task is already running. Wait for it to finish first.")
            return

        def worker():
            self._running = True
            self._set_status("Updating Aiya files")
            try:
                result = update_installation(PROJECT_ROOT)
                self._append_log_async(f"Update completed from {result.get('repo_url')} [{result.get('branch')}]")
            except Exception as exc:
                self._append_log_async(f"Update failed: {exc}")
            finally:
                self._running = False
                self._set_status("Ready")

        threading.Thread(target=worker, daemon=True).start()

    def check_docker(self):
        def worker():
            self._running = True
            self._set_status("Checking Docker")
            try:
                if not self._command_exists("docker"):
                    self._append_log_async("Docker CLI is missing.")
                else:
                    docker_version = subprocess.run(
                        ["docker", "--version"],
                        cwd=PROJECT_ROOT,
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                    self._append_log_async((docker_version.stdout or docker_version.stderr).strip() or "Docker version check returned no output.")
                    engine = subprocess.run(
                        ["docker", "version", "--format", "client={{.Client.Version}} server={{.Server.Version}}"],
                        cwd=PROJECT_ROOT,
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                    engine_output = (engine.stdout or engine.stderr).strip()
                    self._append_log_async(engine_output or "Docker engine is not ready yet.")

                if self._command_exists("wsl"):
                    wsl_status = subprocess.run(
                        ["wsl", "--status"],
                        cwd=PROJECT_ROOT,
                        capture_output=True,
                        text=True,
                        timeout=20,
                    )
                    text = (wsl_status.stdout or wsl_status.stderr).strip()
                    if text:
                        self._append_log_async(text)
            except Exception as exc:
                self._append_log_async(f"Docker check failed: {exc}")
            finally:
                self._running = False
                self._set_status("Ready")

        if self._running:
            self._append_log("Another launcher task is already running. Wait for it to finish first.")
            return
        threading.Thread(target=worker, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    AiyaServerLauncher().run()
