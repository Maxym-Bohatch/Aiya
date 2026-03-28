import base64
import ctypes
import ctypes.wintypes as wintypes
import io
import json
import math
import os
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import ttk

try:
    import winsound
except Exception:
    winsound = None

import requests

from config import settings
from game_control import get_backend
from installer.common import create_scrollable_frame

try:
    from PIL import Image, ImageGrab, ImageSequence, ImageTk
except Exception:
    Image = None
    ImageGrab = None
    ImageSequence = None
    ImageTk = None

try:
    import pytesseract
except Exception:
    pytesseract = None


FIB = [1, 2, 3, 5, 8, 13, 21]
GAMEPAD_PRESETS = {
    "xbox_balanced": {
        "profile_name": "xbox-balanced",
        "input_mode": "gamepad",
        "play_mode": "assist",
        "planner_interval_ms": "2200",
        "action_cooldown_ms": "900",
        "max_actions_per_step": "2",
    },
    "xbox_fast": {
        "profile_name": "xbox-fast",
        "input_mode": "gamepad",
        "play_mode": "auto",
        "planner_interval_ms": "1200",
        "action_cooldown_ms": "420",
        "max_actions_per_step": "3",
    },
    "hybrid_safe": {
        "profile_name": "hybrid-safe",
        "input_mode": "hybrid",
        "play_mode": "assist",
        "planner_interval_ms": "2600",
        "action_cooldown_ms": "1200",
        "max_actions_per_step": "1",
    },
}


@dataclass
class OCRLine:
    text: str
    left: int
    top: int
    width: int
    height: int


class AiyaDesktop:
    def __init__(self, master=None):
        self.api_url = settings.api_url
        self.user_name = settings.client_user_name
        self.external_id = settings.client_external_id
        self.platform = settings.client_platform
        self.backend = get_backend()

        self.ocr_enabled = False
        self.tts_enabled = False
        self.desktop_subtitles_enabled = settings.enable_desktop_subtitles
        self.game_mode_enabled = False
        self.screen_mode = "manual"
        self.game_name = "unknown-game"
        self.game_profile_name = "default"
        self.game_session_id = None
        self.game_last_plan = {}
        self.game_last_actions = []
        self.game_last_action_name = ""
        self.game_last_executed_at = 0.0
        self.game_auto_assess_enabled = True
        self.game_goal = "stay alive and move toward the objective"
        self.last_ocr_text = ""
        self.last_screen_summary = ""
        self.last_translation_signature = ""
        self.translation_region = None
        self.translation_capture_mode = "region"
        self.translation_auto_enabled = False
        self.translation_refresh_seconds = 4
        self.game_waiting_logged = False
        self.animation_tick = 0

        self.overlay_window = None
        self.overlay_canvas = None
        self.subtitle_overlay_window = None
        self.subtitle_overlay_label = None
        self.character_window = None
        self.character_canvas = None
        self.character_label = None
        self.character_frames = []
        self.character_frame_index = 0
        self.character_animation_running = False
        self.character_manifest = {}
        self._mci_alias = "aiya_audio"

        self._owns_root = master is None
        self.root = tk.Tk() if self._owns_root else tk.Toplevel(master)
        self.root.title("Aiya Core")
        self.root.geometry("1280x1040")
        self.root.minsize(1140, 900)
        self.root.configure(bg="#07120e")
        self.root.bind("<F8>", lambda _event: self.capture_once())
        self.root.bind("<F9>", lambda _event: self.toggle_ocr())
        self.root.bind("<F10>", lambda _event: self.toggle_game_mode())
        self.root.bind("<F11>", lambda _event: self.translate_selected_region())

        self.subtitle = tk.StringVar(value="Айя на зв'язку. Core стабільний, можна тестити.")
        self.ocr_status = tk.StringVar(value="OCR: off")
        self.tts_status = tk.StringVar(value="TTS: checking")
        self.game_status = tk.StringVar(value="Game mode: off")
        self.screen_mode_status = tk.StringVar(value="Screen mode: manual")
        self.presence_status = tk.StringVar(value="Aiya Core // white-green channel stable")
        self.translation_source_lang = tk.StringVar(value=settings.client_translation_source_lang)
        self.translation_target_lang = tk.StringVar(value=settings.client_translation_target_lang)
        self.ocr_langs_var = tk.StringVar(value=settings.ocr_languages)
        self.translation_status = tk.StringVar(value="Overlay translator: idle")
        self.game_profile_var = tk.StringVar(value=self.game_profile_name)
        self.gamepad_preset_var = tk.StringVar(value="xbox_balanced")
        self.game_play_mode_var = tk.StringVar(value="assist")
        self.game_input_mode_var = tk.StringVar(value="hybrid")
        self.game_interval_var = tk.StringVar(value="2200")
        self.game_cooldown_var = tk.StringVar(value="900")
        self.game_max_actions_var = tk.StringVar(value="2")
        self.game_simulate_var = tk.BooleanVar(value=False)
        self.game_confirm_var = tk.BooleanVar(value=False)
        self.game_learning_var = tk.BooleanVar(value=True)
        self.game_auto_assess_var = tk.BooleanVar(value=True)
        self.game_profile_status = tk.StringVar(value="Game profile: default // assist")
        self.game_learning_status = tk.StringVar(value="Game learning: idle")
        self.character_status = tk.StringVar(value="Character: loading")
        self.subtitle_overlay_status = tk.StringVar(value="Subtitles overlay: pending")

        self._configure_styles()
        self._build_ui()

        if pytesseract and settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

        self._start_ocr_thread()
        self._start_game_loop()
        self._start_translation_loop()
        self._animate_scene()
        self._ensure_subtitle_overlay()
        self._ensure_character_overlay()
        self._announce_runtime_status()
        self._sync_runtime_flags()
        self.load_game_profile()

    def _configure_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Aiya.TButton",
            background="#173225",
            foreground="#e8fff1",
            borderwidth=0,
            focusthickness=0,
            padding=8,
            font=("Segoe UI Semibold", 10),
        )
        style.map("Aiya.TButton", background=[("active", "#1f4735")])

    def _build_ui(self):
        canvas, shell, scrollbar = create_scrollable_frame(
            self.root,
            self.root,
            canvas_bg="#07120e",
            use_ttk_frame=False,
            frame_bg="#07120e",
        )
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.bg_canvas = tk.Canvas(shell, bg="#07120e", highlightthickness=0)
        self.bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._draw_background(self.bg_canvas)

        content = tk.Frame(shell, bg="#07120e")
        content.pack(fill="both", expand=True, padx=18, pady=18)

        left = tk.Frame(content, bg="#07120e")
        left.pack(side="left", fill="both", expand=True)

        right = tk.Frame(content, bg="#07120e", width=420)
        right.pack(side="right", fill="y", padx=(16, 0))
        right.pack_propagate(False)

        hero = tk.Frame(left, bg="#0d1813", highlightbackground="#264434", highlightthickness=1)
        hero.pack(fill="both", expand=True)

        self.hero_canvas = tk.Canvas(hero, width=720, height=760, bg="#0d1813", highlightthickness=0)
        self.hero_canvas.pack(fill="both", expand=True)
        self.avatar = self._draw_core_visual(self.hero_canvas)

        footer = tk.Frame(left, bg="#07120e")
        footer.pack(fill="x", pady=(14, 0))
        subtitle_card = tk.Frame(footer, bg="#0f1d16", highlightbackground="#214131", highlightthickness=1)
        subtitle_card.pack(fill="x")

        tk.Label(
            subtitle_card,
            text="AIYA CORE // LOCAL CONSOLE",
            bg="#0f1d16",
            fg="#71cf97",
            font=("Consolas", 10, "bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(
            subtitle_card,
            textvariable=self.subtitle,
            bg="#0f1d16",
            fg="#edfff3",
            wraplength=720,
            justify="left",
            padx=16,
            pady=14,
            font=("Segoe UI", 12, "bold"),
        ).pack(fill="x")
        tk.Label(
            subtitle_card,
            textvariable=self.presence_status,
            bg="#0f1d16",
            fg="#8eb7a1",
            font=("Consolas", 9),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 12))

        self._build_side_panel(right)

    def _build_side_panel(self, parent: tk.Frame):
        profile = tk.Frame(parent, bg="#111f18", highlightbackground="#244233", highlightthickness=1)
        profile.pack(fill="x")
        tk.Label(profile, text="AIYA CORE", bg="#111f18", fg="#f3fff6", font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(profile, text="Companion console below, overlays above the desktop", bg="#111f18", fg="#6db38d", font=("Consolas", 10)).pack(anchor="w", padx=16, pady=(0, 12))
        for value in (
            self.ocr_status,
            self.tts_status,
            self.game_status,
            self.game_profile_status,
            self.game_learning_status,
            self.screen_mode_status,
            self.translation_status,
            self.character_status,
            self.subtitle_overlay_status,
        ):
            tk.Label(profile, textvariable=value, bg="#111f18", fg="#bddccc", font=("Segoe UI", 10), anchor="w").pack(fill="x", padx=16, pady=2)

        controls = tk.Frame(parent, bg="#111f18", highlightbackground="#244233", highlightthickness=1)
        controls.pack(fill="x", pady=(14, 0))
        tk.Label(controls, text="Controls", bg="#111f18", fg="#effff4", font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(14, 10))
        grid = tk.Frame(controls, bg="#111f18")
        grid.pack(fill="x", padx=12, pady=(0, 12))
        buttons = [
            ("Sync Status", self._sync_runtime_flags),
            ("Capture Now", self.capture_once),
            ("OCR On/Off", self.toggle_ocr),
            ("TTS On/Off", self.toggle_tts),
            ("Game On/Off", self.toggle_game_mode),
            ("Game Step Now", self.run_game_step_now),
            ("Screen Always", lambda: self.set_screen_mode("always")),
            ("Screen Off", lambda: self.set_screen_mode("off")),
            ("Toggle Subtitles", self.toggle_subtitle_overlay),
            ("Toggle Character", self.toggle_character_overlay),
        ]
        for index, (label, command) in enumerate(buttons):
            row, col = divmod(index, 2)
            ttk.Button(grid, text=label, command=command, style="Aiya.TButton").grid(row=row, column=col, sticky="ew", padx=4, pady=4)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        translate_card = tk.Frame(parent, bg="#13251d", highlightbackground="#244233", highlightthickness=1)
        translate_card.pack(fill="x", pady=(14, 0))
        tk.Label(translate_card, text="Screen Translator", bg="#13251d", fg="#effff4", font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(14, 8))
        lang_row = tk.Frame(translate_card, bg="#13251d")
        lang_row.pack(fill="x", padx=16)
        tk.Label(lang_row, text="From", bg="#13251d", fg="#badcc9", font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(lang_row, textvariable=self.translation_source_lang, width=8, bg="#09150f", fg="#edfff4", insertbackground="#90f5b6", relief="flat").pack(side="left", padx=(8, 16))
        tk.Label(lang_row, text="To", bg="#13251d", fg="#badcc9", font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(lang_row, textvariable=self.translation_target_lang, width=8, bg="#09150f", fg="#edfff4", insertbackground="#90f5b6", relief="flat").pack(side="left", padx=(8, 16))
        tk.Label(lang_row, text="OCR", bg="#13251d", fg="#badcc9", font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(lang_row, textvariable=self.ocr_langs_var, width=12, bg="#09150f", fg="#edfff4", insertbackground="#90f5b6", relief="flat").pack(side="left", padx=(8, 0))
        translate_grid = tk.Frame(translate_card, bg="#13251d")
        translate_grid.pack(fill="x", padx=12, pady=(10, 12))
        translate_buttons = [
            ("Translate Area", self.translate_selected_region),
            ("Translate Window", self.translate_active_window),
            ("Auto Area", self.toggle_auto_region_translation),
            ("Clear Overlay", self.clear_translation_overlay),
        ]
        for index, (label, command) in enumerate(translate_buttons):
            row, col = divmod(index, 2)
            ttk.Button(translate_grid, text=label, command=command, style="Aiya.TButton").grid(row=row, column=col, sticky="ew", padx=4, pady=4)
        translate_grid.columnconfigure(0, weight=1)
        translate_grid.columnconfigure(1, weight=1)

        ask_card = tk.Frame(parent, bg="#13251d", highlightbackground="#244233", highlightthickness=1)
        ask_card.pack(fill="x", pady=(14, 0))
        tk.Label(ask_card, text="Talk to Aiya", bg="#13251d", fg="#effff4", font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(14, 10))
        self.entry = tk.Text(ask_card, height=8, wrap="word", bg="#09150f", fg="#edfff4", insertbackground="#90f5b6", relief="flat", font=("Segoe UI", 11))
        self.entry.pack(fill="x", padx=16)
        ttk.Button(ask_card, text="Send", command=self.ask_from_input, style="Aiya.TButton").pack(anchor="e", padx=16, pady=12)

        game_card = tk.Frame(parent, bg="#111f18", highlightbackground="#244233", highlightthickness=1)
        game_card.pack(fill="x", pady=(14, 0))
        tk.Label(game_card, text="Game Session", bg="#111f18", fg="#effff4", font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(14, 10))
        self.game_name_entry = tk.Entry(game_card, bg="#09150f", fg="#effff4", insertbackground="#90f5b6", relief="flat", font=("Segoe UI", 11))
        self.game_name_entry.insert(0, self.game_name)
        self.game_name_entry.pack(fill="x", padx=16, pady=(0, 8))
        self.game_goal_entry = tk.Entry(game_card, bg="#09150f", fg="#effff4", insertbackground="#90f5b6", relief="flat", font=("Segoe UI", 11))
        self.game_goal_entry.insert(0, self.game_goal)
        self.game_goal_entry.pack(fill="x", padx=16, pady=(0, 8))
        profile_row = tk.Frame(game_card, bg="#111f18")
        profile_row.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(profile_row, text="Profile", bg="#111f18", fg="#badcc9", font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(profile_row, textvariable=self.game_profile_var, width=12, bg="#09150f", fg="#edfff4", insertbackground="#90f5b6", relief="flat").pack(side="left", padx=(8, 16))
        tk.Label(profile_row, text="Mode", bg="#111f18", fg="#badcc9", font=("Segoe UI", 10)).pack(side="left")
        ttk.Combobox(profile_row, textvariable=self.game_play_mode_var, width=10, values=("observe", "assist", "auto"), state="readonly").pack(side="left", padx=(8, 0))
        preset_row = tk.Frame(game_card, bg="#111f18")
        preset_row.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(preset_row, text="Preset", bg="#111f18", fg="#badcc9", font=("Segoe UI", 10)).pack(side="left")
        ttk.Combobox(
            preset_row,
            textvariable=self.gamepad_preset_var,
            width=16,
            values=tuple(GAMEPAD_PRESETS.keys()),
            state="readonly",
        ).pack(side="left", padx=(8, 12))
        ttk.Button(preset_row, text="Apply Preset", command=self.apply_gamepad_preset, style="Aiya.TButton").pack(side="left")
        timing_row = tk.Frame(game_card, bg="#111f18")
        timing_row.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(timing_row, text="Input", bg="#111f18", fg="#badcc9", font=("Segoe UI", 10)).pack(side="left")
        ttk.Combobox(timing_row, textvariable=self.game_input_mode_var, width=9, values=("hybrid", "keyboard", "gamepad"), state="readonly").pack(side="left", padx=(8, 16))
        tk.Label(timing_row, text="Step ms", bg="#111f18", fg="#badcc9", font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(timing_row, textvariable=self.game_interval_var, width=7, bg="#09150f", fg="#edfff4", insertbackground="#90f5b6", relief="flat").pack(side="left", padx=(8, 16))
        tk.Label(timing_row, text="Cooldown", bg="#111f18", fg="#badcc9", font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(timing_row, textvariable=self.game_cooldown_var, width=7, bg="#09150f", fg="#edfff4", insertbackground="#90f5b6", relief="flat").pack(side="left", padx=(8, 0))
        limit_row = tk.Frame(game_card, bg="#111f18")
        limit_row.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(limit_row, text="Actions/step", bg="#111f18", fg="#badcc9", font=("Segoe UI", 10)).pack(side="left")
        tk.Entry(limit_row, textvariable=self.game_max_actions_var, width=5, bg="#09150f", fg="#edfff4", insertbackground="#90f5b6", relief="flat").pack(side="left", padx=(8, 16))
        tk.Checkbutton(limit_row, text="Simulate only", variable=self.game_simulate_var, bg="#111f18", fg="#dfffe8", selectcolor="#09150f", activebackground="#111f18", activeforeground="#dfffe8").pack(side="left")
        tk.Checkbutton(limit_row, text="Confirm", variable=self.game_confirm_var, bg="#111f18", fg="#dfffe8", selectcolor="#09150f", activebackground="#111f18", activeforeground="#dfffe8").pack(side="left", padx=(12, 0))
        toggles_row = tk.Frame(game_card, bg="#111f18")
        toggles_row.pack(fill="x", padx=16, pady=(0, 10))
        tk.Checkbutton(toggles_row, text="Learning", variable=self.game_learning_var, bg="#111f18", fg="#dfffe8", selectcolor="#09150f", activebackground="#111f18", activeforeground="#dfffe8").pack(side="left")
        tk.Checkbutton(toggles_row, text="Auto assess", variable=self.game_auto_assess_var, bg="#111f18", fg="#dfffe8", selectcolor="#09150f", activebackground="#111f18", activeforeground="#dfffe8").pack(side="left", padx=(12, 0))
        game_grid = tk.Frame(game_card, bg="#111f18")
        game_grid.pack(fill="x", padx=12, pady=(0, 12))
        game_buttons = [
            ("Save Profile", self.save_game_profile),
            ("Load Profile", self.load_game_profile),
            ("Good Move", lambda: self.send_game_feedback("good")),
            ("Bad Move", lambda: self.send_game_feedback("bad")),
            ("Goal Reached", lambda: self.send_game_feedback("goal")),
            ("Stuck", lambda: self.send_game_feedback("stuck")),
        ]
        for index, (label, command) in enumerate(game_buttons):
            row, col = divmod(index, 2)
            ttk.Button(game_grid, text=label, command=command, style="Aiya.TButton").grid(row=row, column=col, sticky="ew", padx=4, pady=4)
        game_grid.columnconfigure(0, weight=1)
        game_grid.columnconfigure(1, weight=1)

        log_card = tk.Frame(parent, bg="#111f18", highlightbackground="#244233", highlightthickness=1)
        log_card.pack(fill="both", expand=True, pady=(14, 0))
        tk.Label(log_card, text="Activity", bg="#111f18", fg="#effff4", font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(14, 10))
        self.log = tk.Text(log_card, wrap="word", bg="#09150f", fg="#badcc9", insertbackground="#90f5b6", relief="flat", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def _draw_background(self, canvas: tk.Canvas):
        width = 1400
        height = 900
        canvas.create_rectangle(0, 0, width, height, fill="#07120e", outline="")
        canvas.create_oval(-140, -60, 560, 540, fill="#113123", outline="")
        canvas.create_oval(780, -160, 1380, 340, fill="#0d241a", outline="")
        canvas.create_oval(880, 420, 1500, 1040, fill="#0a1d15", outline="")
        for index in range(12):
            x = 80 + index * 108
            canvas.create_line(x, 0, x - 170, height, fill="#0f2018", width=1)
        for index in range(10):
            y = 70 + index * 86
            canvas.create_line(0, y, width, y - 36, fill="#0d1b14", width=1)

    def _draw_core_visual(self, canvas: tk.Canvas):
        canvas.create_rectangle(0, 0, 900, 740, fill="#0d1813", outline="")
        canvas.create_oval(52, 10, 668, 648, fill="#112a1d", outline="")
        canvas.create_oval(96, 34, 624, 604, fill="#17402b", outline="")
        rings = [
            canvas.create_oval(84, 42, 620, 618, outline="#284c39", width=2),
            canvas.create_oval(118, 74, 586, 586, outline="#71ce98", width=2),
            canvas.create_oval(154, 112, 550, 548, outline="#d1ffe6", width=2),
        ]
        canvas.create_text(86, 54, text="AIYA // CORE", anchor="w", fill="#effff6", font=("Segoe UI", 18, "bold"))
        canvas.create_text(88, 84, text="Companion console with detached overlays", anchor="w", fill="#6ec391", font=("Consolas", 11))
        data_core = canvas.create_oval(314, 226, 390, 322, fill="#8affb3", outline="#eafff3", width=2)
        halo = canvas.create_arc(230, 42, 472, 226, start=18, extent=144, style="arc", outline="#dffff2", width=3)
        halo_inner = canvas.create_arc(248, 60, 456, 212, start=18, extent=144, style="arc", outline="#67d795", width=2)
        eye_left = canvas.create_oval(296, 204, 318, 226, fill="", outline="#79ffae", width=2)
        eye_right = canvas.create_oval(386, 204, 408, 226, fill="", outline="#79ffae", width=2)
        pupil_left = canvas.create_oval(302, 210, 312, 220, fill="#a4ff7c", outline="")
        pupil_right = canvas.create_oval(392, 210, 402, 220, fill="#a4ff7c", outline="")
        mouth = canvas.create_line(320, 292, 352, 302, 386, 292, fill="#dc6f86", width=3, smooth=True)
        particles = []
        particle_bases = []
        for index in range(18):
            angle = (math.pi * 2 / 18) * index
            radius = 224 + (index % 3) * 42
            cx = 352 + math.cos(angle) * radius
            cy = 346 + math.sin(angle) * radius * 0.88
            particle_bases.append((cx, cy))
            particles.append(canvas.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill="#8effbe", outline=""))
        return {
            "rings": rings,
            "data_core": data_core,
            "halo": halo,
            "halo_inner": halo_inner,
            "eye_left": eye_left,
            "eye_right": eye_right,
            "pupil_left": pupil_left,
            "pupil_right": pupil_right,
            "mouth": mouth,
            "particles": particles,
            "particle_bases": particle_bases,
            "mouth_base": [320, 292, 352, 302, 386, 292],
        }

    def _animate_scene(self):
        self.animation_tick += 1
        phase = self.animation_tick / max(1, settings.performance.desktop_fps / 2)
        for index, ring in enumerate(self.avatar["rings"]):
            fib = FIB[index + 1]
            pulse = math.sin(phase / fib) * (6 + index * 4)
            self.hero_canvas.coords(ring, 78 + pulse, 28 + pulse * 0.6, 622 - pulse, 546 - pulse * 0.6)
        for index, particle in enumerate(self.avatar["particles"]):
            fib = FIB[(index % 5) + 1]
            base_x, base_y = self.avatar["particle_bases"][index]
            dx = math.sin(phase / fib) * (6 + fib * 0.22)
            dy = math.cos(phase / (fib + 1)) * (4 + fib * 0.18)
            self.hero_canvas.coords(particle, base_x - 6 + dx, base_y - 6 + dy, base_x + 6 + dx, base_y + 6 + dy)
        blink = self.animation_tick % 180
        eyes_open = not (blink in range(0, 8) or blink in range(96, 103))
        if eyes_open:
            self.hero_canvas.coords(self.avatar["eye_left"], 296, 204, 318, 226)
            self.hero_canvas.coords(self.avatar["eye_right"], 386, 204, 408, 226)
            self.hero_canvas.coords(self.avatar["pupil_left"], 302, 210, 312, 220)
            self.hero_canvas.coords(self.avatar["pupil_right"], 392, 210, 402, 220)
        else:
            self.hero_canvas.coords(self.avatar["eye_left"], 296, 214, 318, 216)
            self.hero_canvas.coords(self.avatar["eye_right"], 386, 214, 408, 216)
            self.hero_canvas.coords(self.avatar["pupil_left"], 0, 0, 0, 0)
            self.hero_canvas.coords(self.avatar["pupil_right"], 0, 0, 0, 0)
        smile = math.sin(phase / 8) * 4
        mouth_base = self.avatar["mouth_base"]
        self.hero_canvas.coords(self.avatar["mouth"], mouth_base[0], mouth_base[1], mouth_base[2], mouth_base[3] + smile, mouth_base[4], mouth_base[5])
        glow = 140 + int((math.sin(phase / 13) + 1) * 35)
        outline = f"#{glow:02x}ffbf"
        inner = f"#{min(255, glow + 30):02x}ffe0"
        self.hero_canvas.itemconfig(self.avatar["halo"], outline=outline)
        self.hero_canvas.itemconfig(self.avatar["halo_inner"], outline=inner)
        self.root.after(int(1000 / max(12, settings.performance.desktop_fps)), self._animate_scene)

    def append_log(self, speaker: str, text: str):
        self.log.insert("end", f"{speaker}: {text}\n\n")
        self.log.see("end")

    def _int_from_var(self, value: str, default: int, min_value: int, max_value: int) -> int:
        try:
            parsed = int(str(value).strip())
        except Exception:
            parsed = default
        return max(min_value, min(max_value, parsed))

    def _current_game_settings(self) -> dict:
        profile_name = self.game_profile_var.get().strip() or "default"
        play_mode = (self.game_play_mode_var.get().strip() or "assist").lower()
        autoplay = play_mode == "auto"
        simulate_only = bool(self.game_simulate_var.get()) or play_mode == "observe"
        return {
            "profile_name": profile_name,
            "autoplay": autoplay,
            "simulate_only": simulate_only,
            "require_confirmation": bool(self.game_confirm_var.get()),
            "learning_enabled": bool(self.game_learning_var.get()),
            "max_actions_per_step": self._int_from_var(self.game_max_actions_var.get(), 2, 0, 4),
            "action_cooldown_ms": self._int_from_var(self.game_cooldown_var.get(), 900, 100, 5000),
            "planner_interval_ms": self._int_from_var(self.game_interval_var.get(), 2200, 300, 12000),
            "preferred_input_mode": self.game_input_mode_var.get().strip() or "hybrid",
            "target_objective": self.game_goal_entry.get().strip(),
            "notes": f"play_mode={play_mode}",
            "profile_settings": {
                "play_mode": play_mode,
                "auto_assess": bool(self.game_auto_assess_var.get()),
            },
        }

    def _apply_game_profile(self, profile: dict):
        if not isinstance(profile, dict):
            return
        self.game_profile_var.set(profile.get("profile_name") or "default")
        autoplay = bool(profile.get("autoplay", False))
        simulate_only = bool(profile.get("simulate_only", False))
        if simulate_only and not autoplay:
            self.game_play_mode_var.set("observe")
        else:
            self.game_play_mode_var.set("auto" if autoplay else "assist")
        self.game_input_mode_var.set(profile.get("preferred_input_mode") or "hybrid")
        self.game_interval_var.set(str(profile.get("planner_interval_ms") or 2200))
        self.game_cooldown_var.set(str(profile.get("action_cooldown_ms") or 900))
        self.game_max_actions_var.set(str(profile.get("max_actions_per_step") or 2))
        self.game_simulate_var.set(simulate_only)
        self.game_confirm_var.set(bool(profile.get("require_confirmation", False)))
        self.game_learning_var.set(bool(profile.get("learning_enabled", True)))
        profile_settings = profile.get("profile_settings") or {}
        self.game_auto_assess_var.set(bool(profile_settings.get("auto_assess", True)))
        target_objective = profile.get("target_objective") or ""
        if target_objective:
            self.game_goal_entry.delete(0, "end")
            self.game_goal_entry.insert(0, target_objective)
        self.game_profile_status.set(
            f"Game profile: {self.game_profile_var.get()} // {self.game_play_mode_var.get()} // {self.game_input_mode_var.get()}"
        )

    def apply_gamepad_preset(self):
        preset = GAMEPAD_PRESETS.get(self.gamepad_preset_var.get(), GAMEPAD_PRESETS["xbox_balanced"])
        self.game_profile_var.set(preset["profile_name"])
        self.game_input_mode_var.set(preset["input_mode"])
        self.game_play_mode_var.set(preset["play_mode"])
        self.game_interval_var.set(preset["planner_interval_ms"])
        self.game_cooldown_var.set(preset["action_cooldown_ms"])
        self.game_max_actions_var.set(preset["max_actions_per_step"])
        self.game_profile_status.set(
            f"Game profile: {self.game_profile_var.get()} // {self.game_play_mode_var.get()} // {self.game_input_mode_var.get()}"
        )
        self.append_log("game", f"Applied gamepad preset '{self.gamepad_preset_var.get()}'.")

    def save_game_profile(self):
        self.game_name = self.game_name_entry.get().strip() or self.game_name
        settings_map = self._current_game_settings()
        try:
            response = requests.post(
                f"{self.api_url}/game/profile",
                json={
                    "platform": self.platform,
                    "external_id": self.external_id,
                    "user_name": self.user_name,
                    "game_name": self.game_name,
                    "profile_name": settings_map["profile_name"],
                    "settings": settings_map,
                },
                timeout=30,
            )
            response.raise_for_status()
            profile = response.json().get("profile", {})
            self.root.after(0, lambda: self._apply_game_profile(profile))
            self.root.after(0, lambda: self.append_log("game", f"Saved profile '{profile.get('profile_name', 'default')}' for {self.game_name}"))
        except Exception as exc:
            self.append_log("system", f"Could not save game profile: {exc}")

    def load_game_profile(self):
        self.game_name = self.game_name_entry.get().strip() or self.game_name
        profile_name = self.game_profile_var.get().strip() or "default"
        try:
            response = requests.get(
                f"{self.api_url}/game/profile/{self.platform}/{self.external_id}",
                params={"game_name": self.game_name, "profile_name": profile_name, "user_name": self.user_name},
                timeout=30,
            )
            response.raise_for_status()
            profile = response.json()
            self.root.after(0, lambda: self._apply_game_profile(profile))
            self.root.after(0, lambda: self.append_log("game", f"Loaded profile '{profile_name}' for {self.game_name}"))
        except Exception as exc:
            self.append_log("system", f"Could not load game profile: {exc}")

    def send_game_feedback(self, verdict: str, note: str = ""):
        self.game_name = self.game_name_entry.get().strip() or self.game_name
        self.game_goal = self.game_goal_entry.get().strip() or self.game_goal
        action_payload = self.game_last_actions[0] if self.game_last_actions else {}
        action_name = ""
        if isinstance(action_payload, dict):
            action_name = action_payload.get("control") or action_payload.get("type") or ""
        try:
            response = requests.post(
                f"{self.api_url}/game/feedback",
                json={
                    "platform": self.platform,
                    "external_id": self.external_id,
                    "user_name": self.user_name,
                    "game_name": self.game_name,
                    "profile_name": self.game_profile_var.get().strip() or "default",
                    "session_id": self.game_session_id,
                    "verdict": verdict,
                    "score": {"good": 1, "progressed": 1, "goal": 3, "bad": -1, "stuck": -2}.get(verdict, 0),
                    "note": note,
                    "screen_summary": self.last_screen_summary,
                    "action_name": action_name,
                    "action_payload": action_payload,
                },
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            session = payload.get("session") or {}
            if session.get("session_id"):
                self.game_session_id = session["session_id"]
            self.game_learning_status.set(f"Game learning: {verdict} noted")
            self.append_log("game-feedback", f"{verdict} recorded for {self.game_name}")
        except Exception as exc:
            self.append_log("system", f"Could not send game feedback: {exc}")

    def _announce_runtime_status(self):
        if not ImageGrab:
            self.append_log("system", "Pillow ImageGrab недоступний. Захоплення екрана не працюватиме.")
        if not pytesseract:
            self.append_log("system", "pytesseract недоступний. OCR і переклад з екрана не працюватимуть.")
        elif not settings.tesseract_cmd:
            self.append_log("system", "Шлях до Tesseract не заданий. OCR запрацює після налаштування AIYA_TESSERACT_CMD.")

    def _sync_runtime_flags(self):
        def worker():
            try:
                response = requests.get(f"{self.api_url}/users/{self.platform}/{self.external_id}/features", timeout=20)
                response.raise_for_status()
                features = response.json()
                capabilities = requests.get(f"{self.api_url}/speech/capabilities", timeout=20).json()

                def apply():
                    self.ocr_enabled = bool(features.get("ocr_enabled", False))
                    self.tts_enabled = bool(features.get("tts_enabled", False))
                    self.desktop_subtitles_enabled = bool(features.get("desktop_subtitles_enabled", True))
                    self.ocr_status.set(f"OCR: {'on' if self.ocr_enabled else 'off'}")
                    self.tts_status.set(
                        f"TTS: {'on' if self.tts_enabled else 'off'} // {capabilities.get('provider')} // "
                        f"delivery={'ok' if capabilities.get('delivery_enabled') else 'off'}"
                    )
                    self.subtitle_overlay_status.set(
                        f"Subtitles overlay: {'on' if self.desktop_subtitles_enabled and self.subtitle_overlay_window else 'off'}"
                    )
                    self.append_log("system", "Синхронізовано feature flags і TTS capabilities.")

                self.root.after(0, apply)
            except Exception as exc:
                self.root.after(0, lambda: self.append_log("system", f"Не вдалося синхронізувати runtime status: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def toggle_ocr(self):
        self.ocr_enabled = not self.ocr_enabled
        self._patch_feature("ocr_enabled", self.ocr_enabled)
        self.ocr_status.set(f"OCR: {'on' if self.ocr_enabled else 'off'}")

    def toggle_tts(self):
        self.tts_enabled = not self.tts_enabled
        self._patch_feature("tts_enabled", self.tts_enabled)
        self.tts_status.set(f"TTS: {'on' if self.tts_enabled else 'off'}")
        self.append_log("system", f"TTS {'увімкнено' if self.tts_enabled else 'вимкнено'}")

    def toggle_game_mode(self):
        self.game_mode_enabled = not self.game_mode_enabled
        self.game_waiting_logged = False
        self.game_name = self.game_name_entry.get().strip() or self.game_name
        self.game_goal = self.game_goal_entry.get().strip() or self.game_goal
        self.game_profile_name = self.game_profile_var.get().strip() or "default"
        self.save_game_profile()
        if self.game_mode_enabled:
            self.set_screen_mode("always")
            self.capture_once()
            self.append_log("system", f"Game mode увімкнено для '{self.game_name}'. Ціль: {self.game_goal}")
        else:
            self.append_log("system", "Game mode вимкнено.")
        self.game_status.set(f"Game mode: {'on' if self.game_mode_enabled else 'off'} ({self.game_name})")
        self.game_profile_status.set(
            f"Game profile: {self.game_profile_name} // {self.game_play_mode_var.get()} // {self.game_input_mode_var.get()}"
        )

    def run_game_step_now(self):
        self.game_name = self.game_name_entry.get().strip() or self.game_name
        self.game_goal = self.game_goal_entry.get().strip() or self.game_goal
        threading.Thread(target=self._capture_then_run_game_step, daemon=True).start()

    def _capture_then_run_game_step(self):
        self._capture_and_send_if_changed(force=True)
        if self.last_screen_summary:
            self._run_game_step_v2()
        else:
            self.root.after(0, lambda: self.append_log("game", "Немає screen summary. Спершу потрібне успішне захоплення екрана."))

    def toggle_subtitle_overlay(self):
        if self.subtitle_overlay_window and self.subtitle_overlay_window.winfo_exists():
            self.subtitle_overlay_window.destroy()
            self.subtitle_overlay_window = None
            self.subtitle_overlay_label = None
            self.subtitle_overlay_status.set("Subtitles overlay: off")
            return
        self._ensure_subtitle_overlay()
        self._update_subtitle_overlay(self.subtitle.get())
        self.subtitle_overlay_status.set("Subtitles overlay: on")

    def toggle_character_overlay(self):
        if self.character_window and self.character_window.winfo_exists():
            self.character_window.destroy()
            self.character_window = None
            self.character_label = None
            self.character_canvas = None
            self.character_status.set("Character: off")
            return
        self._ensure_character_overlay()

    def set_screen_mode(self, mode: str):
        self.screen_mode = mode
        if mode == "off":
            self.ocr_enabled = False
            self._patch_feature("ocr_enabled", False)
        elif mode == "always":
            self.ocr_enabled = True
            self._patch_feature("ocr_enabled", True)
        self.screen_mode_status.set(f"Screen mode: {mode}")
        self.ocr_status.set(f"OCR: {'on' if self.ocr_enabled else 'off'}")

    def _patch_feature(self, field: str, value: bool):
        try:
            response = requests.patch(
                f"{self.api_url}/users/{self.platform}/{self.external_id}/features",
                json={field: value},
                timeout=30,
            )
            response.raise_for_status()
        except Exception as exc:
            self.append_log("system", f"Не вдалося оновити {field}: {exc}")

    def ask_from_input(self):
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        self.append_log("you", text)
        threading.Thread(target=self._ask_api, args=(text,), daemon=True).start()

    def _ask_api(self, text: str):
        try:
            response = requests.post(
                f"{self.api_url}/ask",
                json={"platform": self.platform, "external_id": self.external_id, "user_name": self.user_name, "text": text},
                timeout=180,
            )
            response.raise_for_status()
            data = response.json()
            answer = data.get("answer", "...")
            self.presence_status.set("Aiya Core // response synced")
            if self.tts_enabled and data.get("tts_available"):
                self._play_tts(answer)
        except Exception as exc:
            answer = f"Помилка: {exc}"
            self.presence_status.set("Aiya Core // connection unstable")
        self.root.after(0, lambda: self._set_subtitle(answer))
        self.root.after(0, lambda: self.append_log("aiya", answer))

    def _set_subtitle(self, text: str):
        self.subtitle.set(text)
        self._update_subtitle_overlay(text)

    def _play_tts(self, text: str):
        try:
            response = requests.post(f"{self.api_url}/speech/file", json={"text": text}, timeout=180)
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").lower()
            suffix = ".wav"
            if "ogg" in content_type:
                suffix = ".ogg"
            elif "mpeg" in content_type or "mp3" in content_type:
                suffix = ".mp3"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(response.content)
                temp_path = temp_file.name
            self._play_audio_file(temp_path, suffix)
        except Exception as exc:
            self.root.after(0, lambda: self.append_log("system", f"TTS playback error: {exc}"))

    def _play_audio_file(self, path: str, suffix: str):
        if suffix == ".wav" and winsound:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return
        try:
            winmm = ctypes.windll.winmm
            winmm.mciSendStringW(f"close {self._mci_alias}", None, 0, None)
            winmm.mciSendStringW(f'open "{path}" alias {self._mci_alias}', None, 0, None)
            winmm.mciSendStringW(f"play {self._mci_alias}", None, 0, None)
        except Exception:
            if hasattr(os, "startfile"):
                os.startfile(path)

    def _start_ocr_thread(self):
        def loop():
            while True:
                if self.ocr_enabled and self.screen_mode == "always":
                    self._capture_and_send_if_changed()
                time.sleep(settings.performance.ocr_interval_seconds)

        threading.Thread(target=loop, daemon=True).start()

    def _start_translation_loop(self):
        def loop():
            while True:
                if self.translation_auto_enabled and self.translation_region:
                    self._translate_current_target()
                time.sleep(self.translation_refresh_seconds)

        threading.Thread(target=loop, daemon=True).start()

    def _start_game_loop(self):
        def loop():
            while True:
                if self.game_mode_enabled:
                    if (self.game_play_mode_var.get().strip().lower() or "assist") != "auto":
                        time.sleep(0.25)
                        continue
                    if self.last_screen_summary:
                        self.game_waiting_logged = False
                        self._run_game_step_v2()
                    elif not self.game_waiting_logged:
                        self.game_waiting_logged = True
                        self.root.after(0, lambda: self.append_log("game", "Game mode чекає на свіжий screen summary. Натисни Capture Now або увімкни Screen Always."))
                time.sleep(max(0.3, self._int_from_var(self.game_interval_var.get(), 2200, 300, 12000) / 1000.0))

        threading.Thread(target=loop, daemon=True).start()

    def capture_once(self):
        if self.screen_mode == "off":
            self.append_log("system", "Screen mode is off")
            return
        threading.Thread(target=self._capture_and_send_if_changed, daemon=True).start()

    def _capture_and_send_if_changed(self, force: bool = False):
        text, image_b64 = self._capture_screen_snapshot()
        if text and (force or text != self.last_ocr_text):
            self.last_ocr_text = text
            self._send_screen_observation(text, image_b64)
            self.root.after(0, lambda: self.ocr_status.set(f"OCR: {text[:80]}"))

    def _capture_screen_snapshot(self):
        if not ImageGrab or not pytesseract:
            return "Pillow/pytesseract недоступні", ""
        try:
            shot = ImageGrab.grab()
            langs = self.ocr_langs_var.get().strip() or "ukr+eng"
            text = pytesseract.image_to_string(shot, lang=langs).strip()
            preview = shot.copy()
            preview.thumbnail((896, 896))
            out = io.BytesIO()
            preview.save(out, format="JPEG", quality=82)
            image_b64 = base64.b64encode(out.getvalue()).decode("utf-8")
            return text.replace("\n", " ")[:600], image_b64
        except Exception as exc:
            return f"OCR error: {exc}", ""

    def _send_screen_observation(self, text: str, image_b64: str = ""):
        try:
            if image_b64:
                response = requests.post(
                    f"{self.api_url}/screen/analyze-image",
                    json={
                        "platform": self.platform,
                        "external_id": self.external_id,
                        "user_name": self.user_name,
                        "image_base64": image_b64,
                        "raw_text": text,
                        "source": "desktop_vision",
                    },
                    timeout=120,
                )
            else:
                response = requests.post(
                    f"{self.api_url}/screen/observe",
                    json={
                        "platform": self.platform,
                        "external_id": self.external_id,
                        "user_name": self.user_name,
                        "raw_text": text,
                        "source": "desktop_ocr",
                    },
                    timeout=120,
                )
            if response.ok:
                data = response.json()
                self.last_screen_summary = data.get("summary", "")
                self.presence_status.set("Aiya Core // vision context updated")
        except Exception as exc:
            self.root.after(0, lambda: self.append_log("system", f"screen observe error: {exc}"))

    def _run_game_step(self):
        try:
            response = requests.post(
                f"{self.api_url}/game/plan",
                json={
                    "platform": self.platform,
                    "external_id": self.external_id,
                    "user_name": self.user_name,
                    "game_name": self.game_name,
                    "goal": self.game_goal,
                    "screen_summary": self.last_screen_summary,
                    "capabilities": self.backend.capabilities(),
                },
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            plan = data.get("plan", {})
            actions = plan.get("actions", [])
            reasoning = plan.get("reasoning", "")
            self.root.after(0, lambda: self.append_log("game-plan", reasoning or "Без нових дій."))
            for action in actions:
                ok = self.backend.execute(action)
                self.root.after(0, lambda action=action, ok=ok: self.append_log("game-exec", f"{action} => {'ok' if ok else 'unsupported'}"))
        except Exception as exc:
            self.root.after(0, lambda: self.append_log("system", f"game loop error: {exc}"))

    def _run_game_step_v2(self):
        try:
            settings_map = self._current_game_settings()
            self.game_profile_name = settings_map["profile_name"]
            response = requests.post(
                f"{self.api_url}/game/plan",
                json={
                    "platform": self.platform,
                    "external_id": self.external_id,
                    "user_name": self.user_name,
                    "game_name": self.game_name,
                    "profile_name": self.game_profile_name,
                    "goal": self.game_goal,
                    "screen_summary": self.last_screen_summary,
                    "capabilities": self.backend.capabilities(),
                    "settings": settings_map,
                },
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            self.game_session_id = data.get("session_id") or self.game_session_id
            plan = data.get("plan", {})
            self.game_last_plan = plan
            actions = plan.get("actions", [])
            self.game_last_actions = actions
            reasoning = plan.get("reasoning", "")
            confidence = float(plan.get("confidence", 0.0) or 0.0)
            self.root.after(0, lambda: self.append_log("game-plan", f"{reasoning or 'No new actions.'} // confidence={confidence:.2f}"))
            play_mode = self.game_play_mode_var.get().strip().lower() or "assist"
            if play_mode == "observe":
                if actions:
                    self.root.after(0, lambda: self.append_log("game-sim", f"Observe mode, planned only: {actions}"))
                return
            for action in actions:
                if self.game_confirm_var.get():
                    self.root.after(0, lambda action=action: self.append_log("game-confirm", f"Pending manual approval: {action}"))
                    break
                if self.game_simulate_var.get():
                    ok = True
                    self.root.after(0, lambda action=action: self.append_log("game-sim", f"Simulated: {action}"))
                else:
                    ok = self.backend.execute(action)
                    self.game_last_action_name = action.get("control") or action.get("type") or ""
                    self.game_last_executed_at = time.time()
                    time.sleep(max(0.05, self._int_from_var(self.game_cooldown_var.get(), 900, 100, 5000) / 1000.0))
                self.root.after(0, lambda action=action, ok=ok: self.append_log("game-exec", f"{action} => {'ok' if ok else 'unsupported'}"))
            if actions and self.game_auto_assess_var.get() and not self.game_simulate_var.get():
                threading.Thread(target=self._auto_assess_game_step, daemon=True).start()
        except Exception as exc:
            self.root.after(0, lambda: self.append_log("system", f"game loop error: {exc}"))

    def _auto_assess_game_step(self):
        previous_summary = self.last_screen_summary
        time.sleep(max(0.4, self._int_from_var(self.game_cooldown_var.get(), 900, 100, 5000) / 1000.0))
        self._capture_and_send_if_changed(force=True)
        time.sleep(0.1)
        new_summary = self.last_screen_summary
        if not new_summary:
            return
        verdict = "stuck" if new_summary == previous_summary else "progressed"
        note = "Scene changed after the last move." if verdict == "progressed" else "Scene did not change after the last move."
        threading.Thread(target=self.send_game_feedback, args=(verdict, note), daemon=True).start()

    def translate_selected_region(self):
        self.translation_capture_mode = "region"
        region = self._select_region_interactively()
        if not region:
            self.translation_status.set("Overlay translator: region selection canceled")
            return
        self.translation_region = region
        self.translation_auto_enabled = False
        self._translate_current_target()

    def toggle_auto_region_translation(self):
        if not self.translation_auto_enabled:
            if not self.translation_region or self.translation_capture_mode != "region":
                region = self._select_region_interactively()
                if not region:
                    self.translation_status.set("Overlay translator: auto mode canceled")
                    return
                self.translation_region = region
                self.translation_capture_mode = "region"
            self.translation_auto_enabled = True
            self.translation_status.set("Overlay translator: auto refresh on")
            self._translate_current_target()
        else:
            self.translation_auto_enabled = False
            self.translation_status.set("Overlay translator: auto refresh off")

    def translate_active_window(self):
        self.translation_capture_mode = "window"
        self.translation_auto_enabled = False
        self.translation_status.set("Overlay translator: switch to target window now")
        self.root.iconify()

        def delayed_capture():
            time.sleep(1.2)
            region = self._get_foreground_window_rect()
            self.root.after(0, self.root.deiconify)
            if not region:
                self.root.after(0, lambda: self.translation_status.set("Overlay translator: active window not found"))
                return
            self.translation_region = region
            self._translate_current_target()

        threading.Thread(target=delayed_capture, daemon=True).start()

    def _translate_current_target(self):
        if not self.translation_region:
            return
        threading.Thread(target=self._translate_region_worker, args=(self.translation_region,), daemon=True).start()

    def _translate_region_worker(self, region):
        image = self._capture_region_image(region)
        if image is None:
            self.root.after(0, lambda: self.translation_status.set("Overlay translator: capture failed"))
            return
        lines = self._ocr_lines_from_image(image)
        if not lines:
            self.root.after(0, lambda: self.translation_status.set("Overlay translator: no text detected"))
            return
        signature = "|".join(line.text for line in lines)
        if signature == self.last_translation_signature:
            return
        self.last_translation_signature = signature
        translated_blocks = []
        source_lang = self.translation_source_lang.get().strip() or "auto"
        target_lang = self.translation_target_lang.get().strip() or "uk"
        for line in lines:
            translated_text = self._translate_via_api(line.text, source_lang, target_lang)
            translated_blocks.append((line, translated_text))
        self.root.after(0, lambda: self._render_translation_overlay(region, translated_blocks))
        self.root.after(0, lambda: self.translation_status.set(f"Overlay translator: {len(translated_blocks)} lines translated"))
        self.root.after(0, lambda: self.append_log("translate", f"Translated overlay in {self.translation_capture_mode} mode"))

    def _translate_via_api(self, text: str, source_lang: str, target_lang: str) -> str:
        try:
            response = requests.post(
                f"{self.api_url}/translate",
                json={
                    "text": text,
                    "source_language": source_lang,
                    "target_language": target_lang,
                },
                timeout=120,
            )
            response.raise_for_status()
            payload = response.json()
            return (payload.get("translation") or text).strip() or text
        except Exception as exc:
            self.root.after(0, lambda: self.append_log("translate", f"Translation error: {exc}"))
            return text

    def clear_translation_overlay(self):
        self.translation_auto_enabled = False
        self.last_translation_signature = ""
        if self.overlay_window and self.overlay_window.winfo_exists():
            self.overlay_window.destroy()
        self.overlay_window = None
        self.overlay_canvas = None
        self.translation_status.set("Overlay translator: cleared")

    def _capture_region_image(self, region):
        if not ImageGrab:
            return None
        try:
            left, top, right, bottom = region
            return ImageGrab.grab(bbox=(left, top, right, bottom))
        except Exception:
            return None

    def _ocr_lines_from_image(self, image):
        if not pytesseract:
            return []
        langs = self.ocr_langs_var.get().strip() or "ukr+eng"
        try:
            data = pytesseract.image_to_data(image, lang=langs, output_type=pytesseract.Output.DICT)
        except Exception as exc:
            self.root.after(0, lambda: self.append_log("translate", f"OCR data error: {exc}"))
            return []
        grouped = {}
        count = len(data.get("text", []))
        for index in range(count):
            raw = (data["text"][index] or "").strip()
            if not raw:
                continue
            try:
                confidence = float(data["conf"][index])
            except Exception:
                confidence = -1
            if confidence < 20:
                continue
            key = (data["block_num"][index], data["par_num"][index], data["line_num"][index])
            item = grouped.setdefault(
                key,
                {
                    "words": [],
                    "left": data["left"][index],
                    "top": data["top"][index],
                    "right": data["left"][index] + data["width"][index],
                    "bottom": data["top"][index] + data["height"][index],
                },
            )
            item["words"].append(raw)
            item["left"] = min(item["left"], data["left"][index])
            item["top"] = min(item["top"], data["top"][index])
            item["right"] = max(item["right"], data["left"][index] + data["width"][index])
            item["bottom"] = max(item["bottom"], data["top"][index] + data["height"][index])
        lines = []
        for item in grouped.values():
            text = " ".join(item["words"]).strip()
            if not text:
                continue
            lines.append(
                OCRLine(
                    text=text,
                    left=item["left"],
                    top=item["top"],
                    width=max(1, item["right"] - item["left"]),
                    height=max(1, item["bottom"] - item["top"]),
                )
            )
        return sorted(lines, key=lambda line: (line.top, line.left))

    def _render_translation_overlay(self, region, translated_blocks):
        left, top, right, bottom = region
        width = max(1, right - left)
        height = max(1, bottom - top)
        transparent = "#010203"
        if self.overlay_window and self.overlay_window.winfo_exists():
            self.overlay_window.destroy()
        self.overlay_window = tk.Toplevel(self.root)
        self.overlay_window.overrideredirect(True)
        self.overlay_window.attributes("-topmost", True)
        self.overlay_window.attributes("-alpha", 0.92)
        try:
            self.overlay_window.wm_attributes("-transparentcolor", transparent)
        except Exception:
            pass
        self.overlay_window.configure(bg=transparent)
        self.overlay_window.geometry(f"{width}x{height}+{left}+{top}")
        self.overlay_canvas = tk.Canvas(self.overlay_window, width=width, height=height, bg=transparent, highlightthickness=0)
        self.overlay_canvas.pack(fill="both", expand=True)
        for line, translated_text in translated_blocks:
            font_size = max(10, min(26, int(line.height * 0.85)))
            x1 = max(0, line.left - 3)
            y1 = max(0, line.top - 2)
            x2 = min(width, line.left + line.width + 6)
            y2 = min(height, line.top + line.height + 6)
            self.overlay_canvas.create_rectangle(x1, y1, x2, y2, fill="#101914", outline="#90ff8f", width=1)
            self.overlay_canvas.create_text(
                x1 + 4,
                y1 + 2,
                text=translated_text,
                anchor="nw",
                fill="#effff5",
                width=max(40, x2 - x1 - 8),
                font=("Segoe UI", font_size, "bold"),
            )

    def _ensure_subtitle_overlay(self):
        if not settings.subtitle_overlay_enabled and not self.desktop_subtitles_enabled:
            return
        if self.subtitle_overlay_window and self.subtitle_overlay_window.winfo_exists():
            return
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-alpha", 0.94)
        window.configure(bg="#06110c")
        label = tk.Label(
            window,
            text=self.subtitle.get(),
            bg="#06110c",
            fg=settings.subtitle_color,
            font=("Segoe UI Semibold", 18),
            justify="center",
            wraplength=960,
            padx=18,
            pady=12,
        )
        label.pack(fill="both", expand=True)
        self.subtitle_overlay_window = window
        self.subtitle_overlay_label = label
        self._update_subtitle_overlay(self.subtitle.get())

    def _update_subtitle_overlay(self, text: str):
        if not self.desktop_subtitles_enabled:
            return
        if not self.subtitle_overlay_window or not self.subtitle_overlay_window.winfo_exists():
            return
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(980, max(360, int(screen_width * 0.56)))
        x = max(20, (screen_width - width) // 2)
        y = max(20, screen_height - 170)
        self.subtitle_overlay_window.geometry(f"{width}x92+{x}+{y}")
        self.subtitle_overlay_label.config(text=text)
        self.subtitle_overlay_status.set("Subtitles overlay: on")

    def _resolve_character_source(self):
        raw = settings.character_asset.strip()
        if not raw:
            return None, {}
        source = Path(raw).expanduser()
        manifest = {}
        if source.is_dir():
            manifest_path = source / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    manifest = {}
            idle_name = manifest.get("idle") or "idle.gif"
            candidate = source / idle_name
            if not candidate.exists():
                for name in ("idle.png", "idle.webp", "idle.jpg", "idle.jpeg"):
                    candidate = source / name
                    if candidate.exists():
                        break
            source = candidate
        return source if source.exists() else None, manifest

    def _ensure_character_overlay(self):
        if not settings.character_overlay_enabled:
            self.character_status.set("Character: disabled by config")
            return
        if self.character_window and self.character_window.winfo_exists():
            return
        self.character_window = tk.Toplevel(self.root)
        self.character_window.overrideredirect(True)
        self.character_window.attributes("-topmost", True)
        self.character_window.configure(bg="#010203")
        try:
            self.character_window.wm_attributes("-transparentcolor", "#010203")
        except Exception:
            pass
        self.character_window.attributes("-alpha", 0.97)
        source, manifest = self._resolve_character_source()
        self.character_manifest = manifest
        if source and Image is not None and ImageTk is not None:
            self.character_label = tk.Label(self.character_window, bg="#010203", bd=0)
            self.character_label.pack(fill="both", expand=True)
            self._load_character_frames(source, manifest)
        else:
            self.character_canvas = tk.Canvas(self.character_window, width=320, height=420, bg="#010203", highlightthickness=0)
            self.character_canvas.pack(fill="both", expand=True)
            self._draw_default_character_overlay(self.character_canvas)
        self._position_character_overlay()
        self.character_status.set("Character: on-screen")

    def _load_character_frames(self, source: Path, manifest: dict):
        self.character_frames = []
        scale = float(manifest.get("scale", settings.character_scale or 1.0))
        image = Image.open(source)
        for frame in ImageSequence.Iterator(image) if getattr(image, "is_animated", False) else [image]:
            rendered = frame.convert("RGBA")
            width = max(64, int(rendered.width * scale))
            height = max(64, int(rendered.height * scale))
            rendered = rendered.resize((width, height), Image.LANCZOS)
            self.character_frames.append(ImageTk.PhotoImage(rendered))
        if self.character_frames and self.character_label:
            self.character_label.config(image=self.character_frames[0])
            self.character_label.image = self.character_frames[0]
            if len(self.character_frames) > 1 and not self.character_animation_running:
                self.character_animation_running = True
                self._tick_character_animation()

    def _tick_character_animation(self):
        if not self.character_window or not self.character_window.winfo_exists() or not self.character_frames or not self.character_label:
            self.character_animation_running = False
            return
        self.character_frame_index = (self.character_frame_index + 1) % len(self.character_frames)
        frame = self.character_frames[self.character_frame_index]
        self.character_label.config(image=frame)
        self.character_label.image = frame
        self.root.after(120, self._tick_character_animation)

    def _draw_default_character_overlay(self, canvas: tk.Canvas):
        canvas.create_oval(36, 22, 286, 272, fill="#123123", outline="#78ffae", width=3)
        canvas.create_oval(88, 68, 234, 214, fill="#0f1d16", outline="#ceffe3", width=2)
        canvas.create_oval(118, 104, 148, 134, fill="#90ff9f", outline="")
        canvas.create_oval(172, 104, 202, 134, fill="#90ff9f", outline="")
        canvas.create_line(126, 182, 160, 196, 196, 182, fill="#f07ca1", width=3, smooth=True)
        canvas.create_text(160, 312, text="AIYA", fill="#effff5", font=("Segoe UI", 22, "bold"))
        canvas.create_text(160, 344, text="Character Overlay", fill="#96d7ad", font=("Consolas", 11))
        canvas.create_text(160, 378, text="Додай AIYA_CHARACTER_ASSET,\nщоб підставити свою модель.", fill="#d8ffe7", font=("Segoe UI", 10), justify="center")

    def _position_character_overlay(self):
        if not self.character_window or not self.character_window.winfo_exists():
            return
        width = 340
        height = 520
        dock = (self.character_manifest.get("dock") or settings.character_dock or "right").lower()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = 20 if dock == "left" else screen_width - width - 20
        y = max(20, screen_height - height - 140)
        self.character_window.geometry(f"{width}x{height}+{x}+{y}")

    def _select_region_interactively(self):
        selection = {"bbox": None}
        picker = tk.Toplevel(self.root)
        picker.attributes("-fullscreen", True)
        picker.attributes("-topmost", True)
        picker.attributes("-alpha", 0.25)
        picker.configure(bg="black")
        canvas = tk.Canvas(picker, cursor="cross", bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        start = {"x": 0, "y": 0}
        rect = {"id": None}

        def on_press(event):
            start["x"], start["y"] = event.x, event.y
            rect["id"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#88ffb8", width=3)

        def on_drag(event):
            if rect["id"]:
                canvas.coords(rect["id"], start["x"], start["y"], event.x, event.y)

        def on_release(event):
            selection["bbox"] = (min(start["x"], event.x), min(start["y"], event.y), max(start["x"], event.x), max(start["y"], event.y))
            picker.destroy()

        picker.bind("<Escape>", lambda _event: picker.destroy())
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        picker.grab_set()
        picker.wait_window()
        bbox = selection.get("bbox")
        if not bbox:
            return None
        left, top, right, bottom = bbox
        if right - left < 20 or bottom - top < 20:
            return None
        return bbox

    def _get_foreground_window_rect(self):
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            rect = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)) == 0:
                return None
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
            if right - left < 40 or bottom - top < 40:
                return None
            return (left, top, right, bottom)
        except Exception:
            return None

    def run(self):
        if self._owns_root:
            self.root.mainloop()


if __name__ == "__main__":
    AiyaDesktop().run()
