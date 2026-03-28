from __future__ import annotations

import os
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from installer.common import app_dir, read_install_info, remove_path, schedule_self_delete

ENV_NAMES = {".env", ".env.server", ".env.client", ".env.example", ".env.server.example", ".env.client.example"}
DATA_DIRS = {"postgres_data", "ollama_storage", "open_webui"}
KEEP_ALWAYS = {"AiyaUninstaller.exe", "AiyaUninstaller.cleanup.cmd"}
DESKTOP_SHORTCUTS = {"Aiya Client.lnk", "Aiya Server.lnk"}


def desktop_dir() -> Path:
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"


class UninstallerApp:
    def __init__(self):
        default_dir = app_dir()
        self.root = tk.Tk()
        self.root.title("Aiya Uninstaller")
        self.root.geometry("860x620")
        self.root.minsize(780, 540)
        self.root.configure(bg="#f5f0e6")

        self.dir_var = tk.StringVar(value=str(default_dir))
        self.remove_env_var = tk.BooleanVar(value=False)
        self.remove_data_var = tk.BooleanVar(value=False)
        self.remove_all_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()
        self._load_install_info(default_dir)

    def _build_ui(self):
        shell = ttk.Frame(self.root, padding=16)
        shell.pack(fill="both", expand=True)

        ttk.Label(shell, text="Aiya Uninstaller", font=("Segoe UI", 22, "bold")).pack(anchor="w")
        ttk.Label(shell, text="Removes the installed Aiya files. Docker data removal is optional.", font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 14))

        row = ttk.Frame(shell)
        row.pack(fill="x")
        ttk.Label(row, text="Install Folder").pack(side="left")
        ttk.Entry(row, textvariable=self.dir_var, width=70).pack(side="left", padx=(8, 8), fill="x", expand=True)
        ttk.Button(row, text="Browse", command=self.pick_dir).pack(side="left")

        self.info_label = ttk.Label(shell, text="", font=("Segoe UI", 10))
        self.info_label.pack(anchor="w", pady=(10, 10))

        options = ttk.LabelFrame(shell, text="Removal Options")
        options.pack(fill="x")
        ttk.Checkbutton(options, text="Remove app files", variable=self.remove_all_var).pack(anchor="w", padx=12, pady=6)
        ttk.Checkbutton(options, text="Also remove env files", variable=self.remove_env_var).pack(anchor="w", padx=12, pady=6)
        ttk.Checkbutton(options, text="Also remove Docker data folders", variable=self.remove_data_var).pack(anchor="w", padx=12, pady=6)

        notes = tk.Text(shell, height=8, wrap="word", bg="#fffdf8", relief="solid", font=("Segoe UI", 10))
        notes.pack(fill="x", pady=(12, 10))
        notes.insert(
            "1.0",
            "Recommended safe uninstall for server mode: remove app files, keep env files and keep data folders first.\n"
            "Only remove postgres_data / ollama_storage / open_webui if you are sure you no longer need the models, database, and web state."
        )
        notes.configure(state="disabled")

        actions = ttk.Frame(shell)
        actions.pack(fill="x")
        ttk.Button(actions, text="Reload Info", command=lambda: self._load_install_info(Path(self.dir_var.get()))).pack(side="left")
        ttk.Button(actions, text="Uninstall", command=self.uninstall).pack(side="left", padx=(8, 0))

        ttk.Label(shell, textvariable=self.status_var, font=("Segoe UI", 10, "italic")).pack(anchor="w", pady=(10, 0))
        self.log = tk.Text(shell, wrap="word", bg="#fffdf8", relief="solid", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, pady=(10, 0))

    def pick_dir(self):
        selected = filedialog.askdirectory(initialdir=self.dir_var.get())
        if selected:
            self.dir_var.set(selected)
            self._load_install_info(Path(selected))

    def append_log(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.status_var.set(text)

    def _load_install_info(self, install_dir: Path):
        info = read_install_info(install_dir)
        if info:
            self.info_label.configure(text=f"Detected install: mode={info.get('mode')} branch={info.get('branch')} repo={info.get('repo_url')}")
        else:
            self.info_label.configure(text=f"No {Path('INSTALL_INFO.json')} found. Manual cleanup mode.")

    def uninstall(self):
        if not self.remove_all_var.get() and not self.remove_env_var.get() and not self.remove_data_var.get():
            messagebox.showinfo("Aiya Uninstaller", "Nothing selected for removal.")
            return
        if not messagebox.askyesno("Aiya Uninstaller", "Proceed with uninstall?"):
            return
        threading.Thread(target=self._uninstall_worker, daemon=True).start()

    def _uninstall_worker(self):
        install_dir = Path(self.dir_var.get()).expanduser().resolve()
        if not install_dir.exists():
            self.root.after(0, lambda: messagebox.showerror("Aiya Uninstaller", "Install folder does not exist."))
            return

        keep_names = set(KEEP_ALWAYS)
        if not self.remove_env_var.get():
            keep_names.update(ENV_NAMES)
        if not self.remove_data_var.get():
            keep_names.update(DATA_DIRS)

        if self.remove_all_var.get():
            for item in list(install_dir.iterdir()):
                if item.name in keep_names:
                    self.root.after(0, lambda name=item.name: self.append_log(f"Keeping {name}"))
                    continue
                try:
                    remove_path(item)
                    self.root.after(0, lambda name=item.name: self.append_log(f"Removed {name}"))
                except Exception as exc:
                    self.root.after(0, lambda name=item.name, exc=exc: self.append_log(f"Failed to remove {name}: {exc}"))
        else:
            if self.remove_env_var.get():
                for name in ENV_NAMES:
                    try:
                        remove_path(install_dir / name)
                    except Exception:
                        pass
            if self.remove_data_var.get():
                for name in DATA_DIRS:
                    try:
                        remove_path(install_dir / name)
                    except Exception:
                        pass

        remaining = [item.name for item in install_dir.iterdir()] if install_dir.exists() else []
        self.root.after(0, lambda: self.append_log(f"Remaining items: {remaining}"))

        desktop = desktop_dir()
        for shortcut in DESKTOP_SHORTCUTS:
            try:
                remove_path(desktop / shortcut)
                self.root.after(0, lambda shortcut=shortcut: self.append_log(f"Removed Desktop shortcut {shortcut}"))
            except Exception:
                pass

        exe_path = Path(__file__).resolve()
        try:
            import sys
            if getattr(sys, "frozen", False):
                exe_path = Path(sys.executable).resolve()
        except Exception:
            pass

        if exe_path.parent == install_dir and install_dir.exists() and set(remaining).issubset(KEEP_ALWAYS):
            self.root.after(0, lambda: self.append_log("Scheduling self-delete cleanup."))
            schedule_self_delete(exe_path, install_dir)
        self.root.after(0, lambda: messagebox.showinfo("Aiya Uninstaller", "Uninstall finished."))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    UninstallerApp().run()
