from __future__ import annotations

import io
import os
import subprocess
import shutil
import tempfile
import threading
import zipfile
from datetime import datetime, UTC
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import requests

from installer.common import resource_path, write_install_info
from installer.server_env import write_server_env
from installer.server_setup import ServerSetupDialog, desktop_dir

DEFAULT_REPO_URL = "https://github.com/Maxym-Bohatch/Aiya"
DEFAULT_BRANCH = "main"
DEFAULT_INSTALL_DIR = str(Path.home() / "Aiya")
DOCKER_WINDOWS_INSTALL_DOC = "https://docs.docker.com/desktop/setup/install/windows-install/"

CLIENT_ONLY_PATHS = [
    ".env.client.example",
    "README.md",
    "requirements.txt",
    "config.py",
    "desktop_companion.py",
    "game_control.py",
    "start_client_only.ps1",
    "client",
    "docs/CLIENT_SETUP.md",
    "docs/DOCKER_MIGRATION.md",
    "scripts/client",
]

EXCLUDED_ROOT_NAMES = {".git", "__pycache__", "dist", "build", "release"}
SHORTCUT_PREFIX = "Aiya"


class InstallerApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Aiya Installer")
        self.root.geometry("980x780")
        self.root.minsize(920, 700)
        self.root.configure(bg="#f5f0e6")

        self.repo_var = tk.StringVar(value=DEFAULT_REPO_URL)
        self.branch_var = tk.StringVar(value=DEFAULT_BRANCH)
        self.dir_var = tk.StringVar(value=DEFAULT_INSTALL_DIR)
        self.mode_var = tk.StringVar(value="both")
        self.status_var = tk.StringVar(value="Ready")
        self.prereq_var = tk.StringVar(value="Server prerequisites not checked")
        self.create_client_shortcut_var = tk.BooleanVar(value=True)
        self.create_server_shortcut_var = tk.BooleanVar(value=True)
        self.server_setup_config: dict | None = None

        self._build_ui()

    def _build_ui(self):
        shell = ttk.Frame(self.root, padding=16)
        shell.pack(fill="both", expand=True)

        ttk.Label(shell, text="Aiya GitHub Installer", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(
            shell,
            text="Downloads the project from GitHub and installs client, server, or both with first-run setup.",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(4, 14))

        form = ttk.Frame(shell)
        form.pack(fill="x")

        self._field(form, 0, "Repo URL", self.repo_var)
        self._field(form, 1, "Branch", self.branch_var)
        self._field(form, 2, "Install Folder", self.dir_var, browse=True)

        mode_box = ttk.LabelFrame(shell, text="Install Mode")
        mode_box.pack(fill="x", pady=(14, 10))
        for value, label in [("client", "Client only"), ("server", "Server only"), ("both", "Client + Server")]:
            ttk.Radiobutton(mode_box, text=label, value=value, variable=self.mode_var).pack(anchor="w", padx=12, pady=6)

        shortcut_box = ttk.LabelFrame(shell, text="Desktop Shortcuts")
        shortcut_box.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(shortcut_box, text="Create client shortcut on Desktop", variable=self.create_client_shortcut_var).pack(anchor="w", padx=12, pady=6)
        ttk.Checkbutton(shortcut_box, text="Create server shortcut on Desktop", variable=self.create_server_shortcut_var).pack(anchor="w", padx=12, pady=6)

        prereq_box = ttk.LabelFrame(shell, text="Server Prerequisites")
        prereq_box.pack(fill="x", pady=(0, 10))
        ttk.Label(
            prereq_box,
            text="For server and both modes the installer can start Docker Desktop, wait for Docker, write .env, and build the backend automatically.",
            font=("Segoe UI", 10),
        ).pack(anchor="w", padx=12, pady=(10, 4))
        ttk.Label(prereq_box, textvariable=self.prereq_var, font=("Segoe UI", 10, "italic")).pack(anchor="w", padx=12, pady=(0, 8))
        prereq_actions = ttk.Frame(prereq_box)
        prereq_actions.pack(fill="x", padx=12, pady=(0, 10))
        ttk.Button(prereq_actions, text="Check Docker / WSL", command=self.check_server_prereqs).pack(side="left")
        ttk.Button(prereq_actions, text="Install Docker Desktop", command=self.install_docker_desktop).pack(side="left", padx=(8, 0))
        ttk.Button(prereq_actions, text="Open Docker Docs", command=lambda: self.open_url(DOCKER_WINDOWS_INSTALL_DOC)).pack(side="left", padx=(8, 0))

        notes = tk.Text(shell, height=12, wrap="word", bg="#fffdf8", relief="solid", font=("Segoe UI", 10))
        notes.pack(fill="x", pady=(0, 10))
        notes.insert(
            "1.0",
            "Client only installs the launcher bundle and client-side helpers.\n"
            "Server only installs the backend stack, opens the mandatory .env setup dialog, and can immediately build Docker.\n"
            "Both installs the whole repo, creates both launchers, and can leave two Desktop shortcuts for end users.\n\n"
            "Server setup supports bundled Ollama, an external Ollama URL, or an OpenAI-compatible external API."
        )
        notes.configure(state="disabled")

        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Install", command=self.install).pack(side="left")
        ttk.Button(actions, text="Open Install Folder", command=self.open_install_folder).pack(side="left", padx=(8, 0))

        ttk.Label(shell, textvariable=self.status_var, font=("Segoe UI", 10, "italic")).pack(anchor="w")
        self.log = tk.Text(shell, wrap="word", bg="#fffdf8", relief="solid", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, pady=(10, 0))

    def _field(self, parent, row: int, label: str, variable: tk.StringVar, browse: bool = False):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6, padx=(0, 10))
        ttk.Entry(parent, textvariable=variable, width=80).grid(row=row, column=1, sticky="ew", pady=6)
        if browse:
            ttk.Button(parent, text="Browse", command=self.pick_dir).grid(row=row, column=2, sticky="w", padx=(8, 0))
        parent.columnconfigure(1, weight=1)

    def pick_dir(self):
        selected = filedialog.askdirectory(initialdir=self.dir_var.get() or DEFAULT_INSTALL_DIR)
        if selected:
            self.dir_var.set(selected)

    def append_log(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.status_var.set(text)

    def append_log_async(self, text: str):
        self.root.after(0, lambda: self.append_log(text))

    def open_install_folder(self):
        Path(self.dir_var.get()).mkdir(parents=True, exist_ok=True)
        os.startfile(self.dir_var.get())

    def open_url(self, url: str):
        import webbrowser
        webbrowser.open(url)

    def _command_exists(self, command: str) -> bool:
        return shutil.which(command) is not None

    def check_server_prereqs(self):
        threading.Thread(target=self._check_server_prereqs_worker, daemon=True).start()

    def _check_server_prereqs_worker(self):
        docker_ok = self._command_exists("docker")
        winget_ok = self._command_exists("winget")
        wsl_ok = self._command_exists("wsl")

        details = [
            f"Docker CLI: {'found' if docker_ok else 'missing'}",
            f"winget: {'found' if winget_ok else 'missing'}",
            f"WSL command: {'found' if wsl_ok else 'missing'}",
        ]

        if wsl_ok:
            try:
                completed = subprocess.run(["wsl", "--status"], capture_output=True, text=True, timeout=20)
                output = (completed.stdout or completed.stderr or "").strip()
                if output:
                    details.append("")
                    details.append(output)
            except Exception as exc:
                details.append(f"WSL status check failed: {exc}")

        if docker_ok:
            try:
                completed = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=20)
                details.append((completed.stdout or completed.stderr or "").strip())
            except Exception as exc:
                details.append(f"Docker version check failed: {exc}")

        message = "\n".join(details)
        summary = "Server prerequisites look usable" if docker_ok and wsl_ok else "Server prerequisites need attention"
        self.root.after(0, lambda: self.prereq_var.set(summary))
        self.root.after(0, lambda: self.append_log(message))

    def install_docker_desktop(self):
        threading.Thread(target=self._install_docker_desktop_worker, daemon=True).start()

    def _install_docker_desktop_worker(self):
        if not self._command_exists("winget"):
            self.root.after(0, lambda: self.append_log("winget is missing. Opening Docker docs instead."))
            self.root.after(0, lambda: self.open_url(DOCKER_WINDOWS_INSTALL_DOC))
            return

        self.root.after(0, lambda: self.append_log("Starting Docker Desktop install via winget. Windows may ask for elevation."))
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
            )
            self.root.after(0, lambda: self.prereq_var.set("Docker Desktop installer launched"))
        except Exception as exc:
            self.root.after(0, lambda: self.append_log(f"Failed to launch Docker Desktop install: {exc}"))
            self.root.after(0, lambda: self.open_url(DOCKER_WINDOWS_INSTALL_DOC))

    def install(self):
        mode = self.mode_var.get()
        self.server_setup_config = None
        if mode in {"server", "both"}:
            setup = ServerSetupDialog(self.root).show()
            if setup is None:
                self.append_log("Installation cancelled during server setup.")
                return
            self.server_setup_config = setup
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self):
        try:
            install_dir = Path(self.dir_var.get()).expanduser().resolve()
            install_dir.mkdir(parents=True, exist_ok=True)
            repo_url = self.repo_var.get().strip().rstrip("/")
            branch = self.branch_var.get().strip() or DEFAULT_BRANCH
            mode = self.mode_var.get()

            self.append_log_async(f"Downloading {repo_url} branch {branch}...")
            extracted_root = self._download_repo(repo_url, branch)
            self.append_log_async(f"Downloaded repo snapshot: {extracted_root}")

            if mode == "client":
                self._copy_client_only(extracted_root, install_dir)
            else:
                self._copy_repo_filtered(extracted_root, install_dir)

            self._drop_bundled_files(install_dir, mode)
            if mode in {"server", "both"} and self.server_setup_config:
                self.append_log_async("Writing server .env from installer setup...")
                write_server_env(install_dir, self.server_setup_config)
            self._write_shortcuts(install_dir, mode)
            self._initialize_git_checkout(install_dir, repo_url, branch)
            self._create_desktop_shortcuts(install_dir, mode)
            self._offer_client_prereq_help(mode)
            if mode in {"server", "both"} and self.server_setup_config and self.server_setup_config.get("autostart_server"):
                self._bootstrap_server_install(install_dir, self.server_setup_config)
            write_install_info(
                install_dir,
                {
                    "repo_url": repo_url,
                    "branch": branch,
                    "mode": mode,
                    "installed_at_utc": datetime.now(UTC).isoformat(),
                    "installer_version": "2.0",
                    "server_setup": {
                        "llm_mode": (self.server_setup_config or {}).get("llm_mode", ""),
                        "performance_profile": (self.server_setup_config or {}).get("performance_profile", ""),
                    },
                },
            )
            self.root.after(0, lambda: self.append_log(f"Install completed in {install_dir}"))
            self.root.after(0, lambda: messagebox.showinfo("Aiya Installer", f"Installation finished.\n\nFolder: {install_dir}"))
        except Exception as exc:
            self.root.after(0, lambda: self.append_log(f"Install failed: {exc}"))
            self.root.after(0, lambda: messagebox.showerror("Aiya Installer", str(exc)))

    def _offer_client_prereq_help(self, mode: str):
        if mode not in {"client", "both"}:
            return
        message = (
            "Client mode still needs local prerequisites on the client PC.\n\n"
            "- Tesseract is required for OCR and on-screen translation.\n"
            "- If you run from source instead of the packaged EXE, install Python dependencies too.\n\n"
            "Open the dependency helper after install?"
        )
        self.root.after(0, lambda: self.append_log("Client prerequisite reminder: Tesseract is still needed on the client PC."))
        self.root.after(0, lambda: self._show_client_prereq_prompt(message))

    def _show_client_prereq_prompt(self, message: str):
        if not messagebox.askyesno("Aiya Installer", message):
            return
        if self._command_exists("winget"):
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
                self.append_log("Launched Tesseract install helper.")
                return
            except Exception as exc:
                self.append_log(f"Could not launch Tesseract install helper: {exc}")
        self.append_log("Open the launcher and use 'Check Client Setup' after install.")

    def _initialize_git_checkout(self, install_dir: Path, repo_url: str, branch: str):
        if not self._command_exists("git"):
            self.root.after(0, lambda: self.append_log("Git is not installed, so repository binding was skipped."))
            return
        try:
            if not (install_dir / ".git").exists():
                subprocess.run(["git", "init"], cwd=install_dir, check=True, capture_output=True, text=True, timeout=30)
                self.root.after(0, lambda: self.append_log("Initialized a local git repository in the install folder."))

            remote_result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=install_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if remote_result.returncode == 0:
                subprocess.run(
                    ["git", "remote", "set-url", "origin", repo_url],
                    cwd=install_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            else:
                subprocess.run(
                    ["git", "remote", "add", "origin", repo_url],
                    cwd=install_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

            subprocess.run(
                ["git", "branch", f"--move={branch}"],
                cwd=install_dir,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.root.after(0, lambda: self.append_log(f"Bound install folder to git remote {repo_url} ({branch})."))
        except Exception as exc:
            self.root.after(0, lambda exc=exc: self.append_log(f"Git binding skipped: {exc}"))

    def _download_repo(self, repo_url: str, branch: str) -> Path:
        zip_url = f"{repo_url}/archive/refs/heads/{branch}.zip"
        response = requests.get(zip_url, timeout=120)
        response.raise_for_status()
        temp_dir = Path(tempfile.mkdtemp(prefix="aiya-installer-"))
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            archive.extractall(temp_dir)
        extracted = [path for path in temp_dir.iterdir() if path.is_dir()]
        if not extracted:
            raise RuntimeError("The downloaded archive did not contain a project folder.")
        return extracted[0]

    def _copy_client_only(self, source_root: Path, target_root: Path):
        self.append_log_async("Copying client-only files...")
        for relative in CLIENT_ONLY_PATHS:
            source = source_root / relative
            target = target_root / relative
            if not source.exists():
                continue
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def _copy_repo_filtered(self, source_root: Path, target_root: Path):
        self.append_log_async("Copying repository files...")
        for item in source_root.iterdir():
            if item.name in EXCLUDED_ROOT_NAMES:
                continue
            target = target_root / item.name
            if item.is_dir():
                shutil.copytree(item, target, dirs_exist_ok=True)
            else:
                shutil.copy2(item, target)

    def _drop_bundled_files(self, install_dir: Path, mode: str):
        bundled_client = resource_path("bundle", "AiyaClientLauncher.exe")
        bundled_server = resource_path("bundle", "AiyaServerLauncher.exe")
        bundled_uninstaller = resource_path("bundle", "AiyaUninstaller.exe")
        bundled_env = resource_path("bundle", ".env.client.example")
        bundled_client_doc = resource_path("bundle", "CLIENT_SETUP.md")
        bundled_migration_doc = resource_path("bundle", "DOCKER_MIGRATION.md")

        if mode in {"client", "both"} and bundled_client.exists():
            shutil.copy2(bundled_client, install_dir / "AiyaClientLauncher.exe")
        if mode in {"server", "both"} and bundled_server.exists():
            shutil.copy2(bundled_server, install_dir / "AiyaServerLauncher.exe")
        if bundled_uninstaller.exists():
            shutil.copy2(bundled_uninstaller, install_dir / "AiyaUninstaller.exe")
        if bundled_env.exists():
            shutil.copy2(bundled_env, install_dir / ".env.client.example")
        docs_dir = install_dir / "docs"
        docs_dir.mkdir(exist_ok=True)
        if bundled_client_doc.exists():
            shutil.copy2(bundled_client_doc, docs_dir / "CLIENT_SETUP.md")
        if bundled_migration_doc.exists():
            shutil.copy2(bundled_migration_doc, docs_dir / "DOCKER_MIGRATION.md")

    def _write_shortcuts(self, install_dir: Path, mode: str):
        if mode in {"client", "both"}:
            (install_dir / "Start Aiya Client.cmd").write_text(
                "@echo off\r\ncd /d %~dp0\r\nif exist AiyaClientLauncher.exe (\r\n  start \"\" AiyaClientLauncher.exe\r\n) else (\r\n  powershell -NoProfile -ExecutionPolicy Bypass -File .\\start_client_only.ps1\r\n)\r\n",
                encoding="utf-8",
            )
        if mode in {"server", "both"}:
            (install_dir / "Start Aiya Server.cmd").write_text(
                "@echo off\r\ncd /d %~dp0\r\nif exist AiyaServerLauncher.exe (\r\n  start \"\" AiyaServerLauncher.exe\r\n) else (\r\n  powershell -NoProfile -ExecutionPolicy Bypass -File .\\start_server_only.ps1\r\n)\r\n",
                encoding="utf-8",
            )
            (install_dir / "Install Docker For Server.cmd").write_text(
                "@echo off\r\ncd /d %~dp0\r\npowershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\server\\install_server_prereqs.ps1\r\n",
                encoding="utf-8",
            )
            (install_dir / "Rebuild Aiya Docker.cmd").write_text(
                "@echo off\r\ncd /d %~dp0\r\npowershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\server\\rebuild_docker.ps1\r\n",
                encoding="utf-8",
            )
        (install_dir / "Uninstall Aiya.cmd").write_text(
            "@echo off\r\ncd /d %~dp0\r\nstart \"\" AiyaUninstaller.exe\r\n",
            encoding="utf-8",
        )

    def _create_desktop_shortcuts(self, install_dir: Path, mode: str):
        desktop = desktop_dir()
        desktop.mkdir(parents=True, exist_ok=True)

        if mode in {"client", "both"} and self.create_client_shortcut_var.get():
            self._create_windows_shortcut(
                desktop / f"{SHORTCUT_PREFIX} Client.lnk",
                install_dir / "AiyaClientLauncher.exe",
                install_dir / "AiyaClientLauncher.exe",
                "Launch the Aiya desktop client",
            )
            self.append_log_async(f"Created Desktop shortcut: {desktop / f'{SHORTCUT_PREFIX} Client.lnk'}")

        if mode in {"server", "both"} and self.create_server_shortcut_var.get():
            self._create_windows_shortcut(
                desktop / f"{SHORTCUT_PREFIX} Server.lnk",
                install_dir / "AiyaServerLauncher.exe",
                install_dir / "AiyaServerLauncher.exe",
                "Launch the Aiya server setup and Docker controls",
            )
            self.append_log_async(f"Created Desktop shortcut: {desktop / f'{SHORTCUT_PREFIX} Server.lnk'}")

    def _create_windows_shortcut(self, shortcut_path: Path, target_path: Path, icon_path: Path, description: str):
        icon = icon_path if icon_path.exists() else target_path
        script = (
            "$WshShell = New-Object -ComObject WScript.Shell;"
            f"$Shortcut = $WshShell.CreateShortcut('{str(shortcut_path)}');"
            f"$Shortcut.TargetPath = '{str(target_path)}';"
            f"$Shortcut.WorkingDirectory = '{str(target_path.parent)}';"
            f"$Shortcut.IconLocation = '{str(icon)},0';"
            f"$Shortcut.Description = '{description}';"
            "$Shortcut.Save();"
        )
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _bootstrap_server_install(self, install_dir: Path, config: dict):
        self.append_log_async("Preparing first backend startup...")
        self._run_command(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(install_dir / "start_server_only.ps1")],
            cwd=install_dir,
            timeout=60 * 60 * 1000,
        )
        self._wait_for_url("http://localhost:8000/health", seconds=240, label="API")
        self._wait_for_url("http://localhost:3000/", seconds=180, label="Aiya web UI")
        if config.get("llm_mode") != "external_api":
            try:
                self._wait_for_url("http://localhost:3001/", seconds=180, label="Open WebUI")
            except Exception as exc:
                self.append_log_async(f"Open WebUI readiness check failed: {exc}")

    def _wait_for_url(self, url: str, seconds: int, label: str):
        self.append_log_async(f"Waiting for {label}: {url}")
        deadline = datetime.now().timestamp() + seconds
        while datetime.now().timestamp() < deadline:
            try:
                response = requests.get(url, timeout=8)
                if response.ok:
                    self.append_log_async(f"{label} is ready.")
                    return
            except Exception:
                pass
            threading.Event().wait(2)
        raise RuntimeError(f"{label} did not become ready in time.")

    def _run_command(self, command: list[str], cwd: Path, timeout: int):
        self.append_log_async(f"Running: {' '.join(command)}")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            assert process.stdout is not None
            for line in process.stdout:
                text = line.rstrip()
                if text:
                    self.append_log_async(text)
            return_code = process.wait(timeout=timeout / 1000)
        except Exception:
            process.kill()
            raise
        if return_code != 0:
            raise RuntimeError(f"Command failed with exit code {return_code}: {' '.join(command)}")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    InstallerApp().run()
