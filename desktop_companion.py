import base64
import ctypes
import io
import math
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

try:
    import winsound
except Exception:
    winsound = None

import requests

from config import settings
from game_control import get_backend
from translation_engine import translate_text

try:
    from PIL import ImageGrab
except Exception:
    ImageGrab = None

try:
    import pytesseract
except Exception:
    pytesseract = None


FIB = [1, 2, 3, 5, 8, 13, 21]


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
        self.ocr_enabled = False
        self.tts_enabled = False
        self.game_mode_enabled = False
        self.screen_mode = "manual"
        self.game_name = "unknown-game"
        self.game_goal = "вижити і навчитись базовим діям"
        self.last_ocr_text = ""
        self.last_screen_summary = ""
        self.backend = get_backend()
        self.animation_tick = 0
        self.overlay_window = None
        self.overlay_canvas = None
        self.translation_region = None
        self.translation_capture_mode = "region"
        self.translation_auto_enabled = False
        self.last_translation_signature = ""
        self.translation_refresh_seconds = 4

        self._owns_root = master is None
        self.root = tk.Tk() if self._owns_root else tk.Toplevel(master)
        self.root.title("Aiya Fairy")
        self.root.geometry("1280x1040")
        self.root.minsize(1100, 900)
        self.root.configure(bg="#07120e")
        self.root.attributes("-topmost", True)
        self.root.bind("<F8>", lambda _event: self.capture_once())
        self.root.bind("<F9>", lambda _event: self.toggle_ocr())
        self.root.bind("<F10>", lambda _event: self.toggle_game_mode())
        self.root.bind("<F11>", lambda _event: self.translate_selected_region())

        self.subtitle = tk.StringVar(value="Айя на зв'язку. Техно-фея готова до розмови.")
        self.ocr_status = tk.StringVar(value="OCR: off")
        self.game_status = tk.StringVar(value="Game mode: off")
        self.screen_mode_status = tk.StringVar(value="Screen mode: manual")
        self.presence_status = tk.StringVar(value="Fairy Frame // white-green channel stable")
        self.translation_source_lang = tk.StringVar(value="auto")
        self.translation_target_lang = tk.StringVar(value="uk")
        self.translation_status = tk.StringVar(value="Overlay translator: idle")

        self._configure_styles()
        self._build_ui()
        self._start_ocr_thread()
        self._start_game_loop()
        self._start_translation_loop()
        self._animate_scene()

        if pytesseract and settings.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        self._announce_runtime_status()

    def _announce_runtime_status(self):
        if not ImageGrab:
            self.append_log("system", "Pillow ImageGrab недоступний. Захоплення екрана не працюватиме.")
        if not pytesseract:
            self.append_log("system", "pytesseract недоступний. OCR і переклад з екрана не працюватимуть.")
        elif not settings.tesseract_cmd:
            self.append_log("system", "Шлях до Tesseract не заданий. OCR запрацює після налаштування AIYA_TESSERACT_CMD.")

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
        shell = tk.Frame(self.root, bg="#07120e")
        shell.pack(fill="both", expand=True)

        self.bg_canvas = tk.Canvas(shell, bg="#07120e", highlightthickness=0)
        self.bg_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._draw_background(self.bg_canvas)

        content = tk.Frame(shell, bg="#07120e")
        content.pack(fill="both", expand=True, padx=18, pady=18)

        left = tk.Frame(content, bg="#07120e")
        left.pack(side="left", fill="both", expand=True)

        right = tk.Frame(content, bg="#07120e", width=380)
        right.pack(side="right", fill="y", padx=(16, 0))
        right.pack_propagate(False)

        hero = tk.Frame(left, bg="#0d1813", highlightbackground="#264434", highlightthickness=1)
        hero.pack(fill="both", expand=True)

        self.hero_canvas = tk.Canvas(hero, width=720, height=760, bg="#0d1813", highlightthickness=0)
        self.hero_canvas.pack(fill="both", expand=True)
        self.avatar = self._draw_fairy(self.hero_canvas)

        footer = tk.Frame(left, bg="#07120e")
        footer.pack(fill="x", pady=(14, 0))
        subtitle_card = tk.Frame(footer, bg="#0f1d16", highlightbackground="#214131", highlightthickness=1)
        subtitle_card.pack(fill="x")

        tk.Label(subtitle_card, text="AIYA // FAIRY CHANNEL", bg="#0f1d16", fg="#71cf97", font=("Consolas", 10, "bold"), anchor="w").pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(subtitle_card, textvariable=self.subtitle, bg="#0f1d16", fg="#edfff3", wraplength=720, justify="left", padx=16, pady=14, font=("Segoe UI", 12, "bold")).pack(fill="x")
        tk.Label(subtitle_card, textvariable=self.presence_status, bg="#0f1d16", fg="#8eb7a1", font=("Consolas", 9), anchor="w").pack(fill="x", padx=16, pady=(0, 12))

        self._build_side_panel(right)

    def _build_side_panel(self, parent: tk.Frame):
        profile = tk.Frame(parent, bg="#111f18", highlightbackground="#244233", highlightthickness=1)
        profile.pack(fill="x")
        tk.Label(profile, text="AIYA", bg="#111f18", fg="#f3fff6", font=("Segoe UI", 22, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(profile, text="White-green techno fairy frame", bg="#111f18", fg="#6db38d", font=("Consolas", 10)).pack(anchor="w", padx=16, pady=(0, 12))
        for value in (self.ocr_status, self.game_status, self.screen_mode_status, self.translation_status):
            tk.Label(profile, textvariable=value, bg="#111f18", fg="#bddccc", font=("Segoe UI", 10), anchor="w").pack(fill="x", padx=16, pady=2)

        controls = tk.Frame(parent, bg="#111f18", highlightbackground="#244233", highlightthickness=1)
        controls.pack(fill="x", pady=(14, 0))
        tk.Label(controls, text="Controls", bg="#111f18", fg="#effff4", font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=16, pady=(14, 10))
        grid = tk.Frame(controls, bg="#111f18")
        grid.pack(fill="x", padx=12, pady=(0, 12))
        buttons = [
            ("OCR On/Off", self.toggle_ocr),
            ("Capture Now", self.capture_once),
            ("TTS On/Off", self.toggle_tts),
            ("Game On/Off", self.toggle_game_mode),
            ("Screen Off", lambda: self.set_screen_mode("off")),
            ("Screen Always", lambda: self.set_screen_mode("always")),
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
        tk.Entry(lang_row, textvariable=self.translation_target_lang, width=8, bg="#09150f", fg="#edfff4", insertbackground="#90f5b6", relief="flat").pack(side="left", padx=(8, 0))
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
        self.game_name_entry.pack(fill="x", padx=16, pady=(0, 12))

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
        for i in range(12):
            x = 80 + i * 108
            canvas.create_line(x, 0, x - 170, height, fill="#0f2018", width=1)
        for i in range(10):
            y = 70 + i * 86
            canvas.create_line(0, y, width, y - 36, fill="#0d1b14", width=1)

    def _draw_fairy(self, canvas: tk.Canvas):
        canvas.create_rectangle(0, 0, 900, 740, fill="#0d1813", outline="")
        canvas.create_oval(52, 10, 668, 648, fill="#112a1d", outline="")
        canvas.create_oval(96, 34, 624, 604, fill="#17402b", outline="")
        rings = [
            canvas.create_oval(84, 42, 620, 618, outline="#284c39", width=2),
            canvas.create_oval(118, 74, 586, 586, outline="#71ce98", width=2),
            canvas.create_oval(154, 112, 550, 548, outline="#d1ffe6", width=2),
        ]
        core_panel = canvas.create_oval(188, 126, 516, 494, fill="#10271d", outline="#2a4a39", width=2)
        inner_panel = canvas.create_oval(220, 156, 484, 462, fill="#0d1c15", outline="#68d88f", width=2)
        center_hex = canvas.create_polygon(352, 202, 414, 238, 414, 310, 352, 346, 290, 310, 290, 238, fill="#173726", outline="#88ffb8", width=3, smooth=True)
        data_core = canvas.create_oval(314, 226, 390, 322, fill="#8affb3", outline="#eafff3", width=2)
        status_fill = canvas.create_rectangle(258, 398, 386, 414, fill="#88ffb8", outline="")
        side_hexes = []
        for coords in ((248, 236, 22), (456, 236, 22), (226, 336, 18), (478, 336, 18), (352, 438, 20)):
            cx, cy, radius = coords
            points = []
            for index in range(6):
                angle = math.pi / 6 + index * math.pi / 3
                points.extend([cx + math.cos(angle) * radius, cy + math.sin(angle) * radius])
            side_hexes.append(canvas.create_polygon(*points, fill="#12291e", outline="#78ffac", width=2))
        particles = []
        particle_bases = []
        for index in range(18):
            angle = (math.pi * 2 / 18) * index
            radius = 224 + (index % 3) * 42
            cx = 352 + math.cos(angle) * radius
            cy = 346 + math.sin(angle) * radius * 0.88
            particle_bases.append((cx, cy))
            particles.append(canvas.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill="#8effbe", outline=""))
        halo = canvas.create_arc(230, 42, 472, 226, start=18, extent=144, style="arc", outline="#dffff2", width=3)
        halo_inner = canvas.create_arc(248, 60, 456, 212, start=18, extent=144, style="arc", outline="#67d795", width=2)
        eye_left = canvas.create_oval(296, 204, 318, 226, fill="", outline="#79ffae", width=2)
        eye_right = canvas.create_oval(386, 204, 408, 226, fill="", outline="#79ffae", width=2)
        pupil_left = canvas.create_oval(302, 210, 312, 220, fill="#a4ff7c", outline="")
        pupil_right = canvas.create_oval(392, 210, 402, 220, fill="#a4ff7c", outline="")
        light_left = canvas.create_oval(304, 212, 308, 216, fill="#ffffff", outline="")
        light_right = canvas.create_oval(394, 212, 398, 216, fill="#ffffff", outline="")
        mouth = canvas.create_line(320, 292, 352, 302, 386, 292, fill="#dc6f86", width=3, smooth=True)
        arc_left = canvas.create_arc(120, 168, 302, 396, start=102, extent=132, style="arc", outline="#8dffbc", width=2)
        arc_right = canvas.create_arc(402, 168, 584, 396, start=-54, extent=132, style="arc", outline="#8dffbc", width=2)
        canvas.create_text(86, 54, text="AIYA // FAIRY LINK", anchor="w", fill="#effff6", font=("Segoe UI", 18, "bold"))
        canvas.create_text(88, 84, text="Living techno-fairy frame with honeycomb butterfly wings", anchor="w", fill="#6ec391", font=("Consolas", 11))
        canvas.create_text(88, 118, text="1 1 2 3 5 8 13 21", anchor="w", fill="#b8ffd5", font=("Consolas", 10, "bold"))
        return {"rings": rings, "core_panel": core_panel, "inner_panel": inner_panel, "center_hex": center_hex, "data_core": data_core, "status_fill": status_fill, "side_hexes": side_hexes, "particles": particles, "halo": halo, "halo_inner": halo_inner, "eye_left": eye_left, "eye_right": eye_right, "pupil_left": pupil_left, "pupil_right": pupil_right, "light_left": light_left, "light_right": light_right, "mouth": mouth, "arc_left": arc_left, "arc_right": arc_right, "particle_bases": particle_bases, "mouth_base": [320, 292, 352, 302, 386, 292]}

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
            self.hero_canvas.coords(self.avatar["light_left"], 304, 212, 308, 216)
            self.hero_canvas.coords(self.avatar["light_right"], 394, 212, 398, 216)
        else:
            self.hero_canvas.coords(self.avatar["eye_left"], 296, 214, 318, 216)
            self.hero_canvas.coords(self.avatar["eye_right"], 386, 214, 408, 216)
            self.hero_canvas.coords(self.avatar["pupil_left"], 0, 0, 0, 0)
            self.hero_canvas.coords(self.avatar["pupil_right"], 0, 0, 0, 0)
            self.hero_canvas.coords(self.avatar["light_left"], 0, 0, 0, 0)
            self.hero_canvas.coords(self.avatar["light_right"], 0, 0, 0, 0)
        smile = math.sin(phase / 8) * 4
        mouth_base = self.avatar["mouth_base"]
        self.hero_canvas.coords(self.avatar["mouth"], mouth_base[0], mouth_base[1], mouth_base[2], mouth_base[3] + smile, mouth_base[4], mouth_base[5])
        glow = 140 + int((math.sin(phase / 13) + 1) * 35)
        outer = f"#{glow:02x}ffbf"
        inner = f"#{min(255, glow + 30):02x}ffe0"
        self.hero_canvas.itemconfig(self.avatar["halo"], outline=outer)
        self.hero_canvas.itemconfig(self.avatar["halo_inner"], outline=inner)
        self.hero_canvas.itemconfig(self.avatar["arc_left"], outline=outer)
        self.hero_canvas.itemconfig(self.avatar["arc_right"], outline=outer)
        self.hero_canvas.itemconfig(self.avatar["eye_left"], outline=outer)
        self.hero_canvas.itemconfig(self.avatar["eye_right"], outline=outer)
        self.root.after(int(1000 / max(12, settings.performance.desktop_fps)), self._animate_scene)

    def append_log(self, speaker: str, text: str):
        self.log.insert("end", f"{speaker}: {text}\n\n")
        self.log.see("end")

    def toggle_ocr(self):
        self.ocr_enabled = not self.ocr_enabled
        self._patch_feature("ocr_enabled", self.ocr_enabled)
        self.ocr_status.set(f"OCR: {'on' if self.ocr_enabled else 'off'}")

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

    def toggle_tts(self):
        self.tts_enabled = not self.tts_enabled
        self._patch_feature("tts_enabled", self.tts_enabled)
        self.append_log("system", f"TTS {'увімкнено' if self.tts_enabled else 'вимкнено'}")

    def toggle_game_mode(self):
        self.game_mode_enabled = not self.game_mode_enabled
        self.game_name = self.game_name_entry.get().strip() or self.game_name
        self.game_status.set(f"Game mode: {'on' if self.game_mode_enabled else 'off'} ({self.game_name})")

    def _patch_feature(self, field: str, value: bool):
        try:
            requests.patch(f"{self.api_url}/users/{self.platform}/{self.external_id}/features", json={field: value}, timeout=30)
        except Exception as e:
            self.append_log("system", f"Не вдалося оновити {field}: {e}")

    def ask_from_input(self):
        text = self.entry.get("1.0", "end").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        self.append_log("you", text)
        threading.Thread(target=self._ask_api, args=(text,), daemon=True).start()

    def _ask_api(self, text: str):
        try:
            response = requests.post(f"{self.api_url}/ask", json={"platform": self.platform, "external_id": self.external_id, "user_name": self.user_name, "text": text}, timeout=180)
            response.raise_for_status()
            data = response.json()
            answer = data.get("answer", "...")
            self.presence_status.set("Fairy Frame // response synced")
            if self.tts_enabled and data.get("tts_available"):
                self._play_tts(answer)
        except Exception as e:
            answer = f"Помилка: {e}"
            self.presence_status.set("Fairy Frame // connection unstable")
        self.root.after(0, lambda: self.subtitle.set(answer))
        self.root.after(0, lambda: self.append_log("aiya", answer))

    def _play_tts(self, text: str):
        if not winsound:
            return
        try:
            response = requests.post(f"{self.api_url}/speech/file", json={"text": text}, timeout=180)
            response.raise_for_status()
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "wav" not in content_type and "wave" not in content_type:
                self.root.after(0, lambda: self.append_log("system", "Локальне відтворення companion зараз підтримує лише WAV-аудіо."))
                return
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
                temp_file.write(response.content)
                temp_path = temp_file.name
            winsound.PlaySound(temp_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            self.root.after(0, lambda: self.append_log("system", f"TTS playback error: {e}"))

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

    def capture_once(self):
        if self.screen_mode == "off":
            self.append_log("system", "Screen mode is off")
            return
        threading.Thread(target=self._capture_and_send_if_changed, daemon=True).start()

    def _capture_and_send_if_changed(self):
        text, image_b64 = self._capture_screen_snapshot()
        if text and text != self.last_ocr_text:
            self.last_ocr_text = text
            self._send_screen_observation(text, image_b64)
            self.root.after(0, lambda: self.ocr_status.set(f"OCR: {text[:80]}"))

    def _send_screen_observation(self, text: str, image_b64: str = ""):
        try:
            if image_b64:
                response = requests.post(f"{self.api_url}/screen/analyze-image", json={"platform": self.platform, "external_id": self.external_id, "user_name": self.user_name, "image_base64": image_b64, "raw_text": text, "source": "desktop_vision"}, timeout=120)
            else:
                response = requests.post(f"{self.api_url}/screen/observe", json={"platform": self.platform, "external_id": self.external_id, "user_name": self.user_name, "raw_text": text, "source": "desktop_ocr"}, timeout=120)
            if response.ok:
                data = response.json()
                self.last_screen_summary = data.get("summary", "")
                self.presence_status.set("Fairy Frame // vision context updated")
        except Exception as e:
            self.root.after(0, lambda: self.append_log("system", f"screen observe error: {e}"))

    def _start_game_loop(self):
        def loop():
            while True:
                if self.game_mode_enabled and self.last_screen_summary:
                    self._run_game_step()
                time.sleep(settings.performance.screen_summary_interval_seconds)
        threading.Thread(target=loop, daemon=True).start()

    def _run_game_step(self):
        try:
            response = requests.post(f"{self.api_url}/game/plan", json={"platform": self.platform, "external_id": self.external_id, "user_name": self.user_name, "game_name": self.game_name, "goal": self.game_goal, "screen_summary": self.last_screen_summary, "capabilities": self.backend.capabilities()}, timeout=120)
            response.raise_for_status()
            data = response.json()
            plan = data.get("plan", {})
            actions = plan.get("actions", [])
            if actions:
                self.root.after(0, lambda: self.append_log("game-plan", plan.get("reasoning", "")))
            for action in actions:
                ok = self.backend.execute(action)
                self.root.after(0, lambda action=action, ok=ok: self.append_log("game-exec", f"{action} => {'ok' if ok else 'unsupported'}"))
        except Exception as e:
            self.root.after(0, lambda: self.append_log("system", f"game loop error: {e}"))

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
            result = translate_text(line.text, source_lang=source_lang, target_lang=target_lang)
            translated_text = result.get("translation", line.text) if result.get("ok") else line.text
            translated_blocks.append((line, translated_text))
        self.root.after(0, lambda: self._render_translation_overlay(region, translated_blocks))
        self.root.after(0, lambda: self.translation_status.set(f"Overlay translator: {len(translated_blocks)} lines translated"))
        self.root.after(0, lambda: self.append_log("translate", f"Translated overlay in {self.translation_capture_mode} mode"))

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
        try:
            data = pytesseract.image_to_data(image, lang="ukr+eng", output_type=pytesseract.Output.DICT)
        except Exception as exc:
            self.root.after(0, lambda exc=exc: self.append_log("translate", f"OCR data error: {exc}"))
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
            item = grouped.setdefault(key, {"words": [], "left": data["left"][index], "top": data["top"][index], "right": data["left"][index] + data["width"][index], "bottom": data["top"][index] + data["height"][index]})
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
            lines.append(OCRLine(text=text, left=item["left"], top=item["top"], width=max(1, item["right"] - item["left"]), height=max(1, item["bottom"] - item["top"])))
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
            self.overlay_canvas.create_rectangle(x1, y1, x2, y2, fill="#101914", outline="#5fe08d", width=1)
            self.overlay_canvas.create_text(x1 + 4, y1 + 2, text=translated_text, anchor="nw", fill="#effff5", width=max(40, x2 - x1 - 8), font=("Segoe UI", font_size, "bold"))

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
            rect = ctypes.wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)) == 0:
                return None
            left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
            if right - left < 40 or bottom - top < 40:
                return None
            return (left, top, right, bottom)
        except Exception:
            return None

    def _capture_screen_snapshot(self):
        if not ImageGrab or not pytesseract:
            return "Pillow/pytesseract недоступні", ""
        try:
            shot = ImageGrab.grab()
            text = pytesseract.image_to_string(shot, lang="ukr+eng").strip()
            preview = shot.copy()
            preview.thumbnail((896, 896))
            out = io.BytesIO()
            preview.save(out, format="JPEG", quality=82)
            image_b64 = base64.b64encode(out.getvalue()).decode("utf-8")
            return text.replace("\n", " ")[:600], image_b64
        except Exception as e:
            return f"OCR error: {e}", ""

    def run(self):
        if self._owns_root:
            self.root.mainloop()


if __name__ == "__main__":
    AiyaDesktop().run()
