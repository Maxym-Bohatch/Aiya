import ctypes
import time

try:
    import vgamepad as vg
except Exception:
    vg = None


VK_CODES = {
    "w": 0x57,
    "a": 0x41,
    "s": 0x53,
    "d": 0x44,
    "space": 0x20,
    "shift": 0x10,
    "ctrl": 0x11,
    "enter": 0x0D,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
}

XUSB_MAP = {
    "a": "XUSB_GAMEPAD_A",
    "b": "XUSB_GAMEPAD_B",
    "x": "XUSB_GAMEPAD_X",
    "y": "XUSB_GAMEPAD_Y",
    "lb": "XUSB_GAMEPAD_LEFT_SHOULDER",
    "rb": "XUSB_GAMEPAD_RIGHT_SHOULDER",
    "start": "XUSB_GAMEPAD_START",
    "back": "XUSB_GAMEPAD_BACK",
    "up": "XUSB_GAMEPAD_DPAD_UP",
    "down": "XUSB_GAMEPAD_DPAD_DOWN",
    "left": "XUSB_GAMEPAD_DPAD_LEFT",
    "right": "XUSB_GAMEPAD_DPAD_RIGHT",
}


class WindowsKeyboardBackend:
    mode = "keyboard"

    def __init__(self):
        self.user32 = ctypes.windll.user32

    def press(self, control: str, duration_ms: int = 120):
        key = VK_CODES.get(control.lower())
        if key is None:
            return False
        self.user32.keybd_event(key, 0, 0, 0)
        time.sleep(max(0.03, duration_ms / 1000))
        self.user32.keybd_event(key, 0, 2, 0)
        return True

    def execute(self, action: dict):
        if action.get("type") != "press":
            return False
        return self.press(action.get("control", ""), action.get("duration_ms", 120))


class VirtualGamepadBackend:
    mode = "gamepad"

    def __init__(self):
        if vg is None:
            raise RuntimeError("vgamepad is unavailable")
        self.pad = vg.VX360Gamepad()

    def press_button(self, control: str, duration_ms: int = 120):
        field_name = XUSB_MAP.get(control.lower())
        if not field_name:
            return False
        button = getattr(vg.XUSB_BUTTON, field_name)
        self.pad.press_button(button=button)
        self.pad.update()
        time.sleep(max(0.03, duration_ms / 1000))
        self.pad.release_button(button=button)
        self.pad.update()
        return True

    def move_left_stick(self, x: float, y: float, duration_ms: int = 180):
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        self.pad.left_joystick_float(x_value_float=x, y_value_float=y)
        self.pad.update()
        time.sleep(max(0.03, duration_ms / 1000))
        self.pad.left_joystick_float(x_value_float=0.0, y_value_float=0.0)
        self.pad.update()
        return True

    def execute(self, action: dict):
        action_type = action.get("type")
        if action_type == "gamepad_button":
            return self.press_button(action.get("control", ""), action.get("duration_ms", 120))
        if action_type == "move_left_stick":
            return self.move_left_stick(
                float(action.get("x", 0.0)),
                float(action.get("y", 0.0)),
                int(action.get("duration_ms", 180)),
            )
        if action_type == "press":
            return False
        return False


class HybridBackend:
    def __init__(self, keyboard_backend, gamepad_backend=None):
        self.keyboard_backend = keyboard_backend
        self.gamepad_backend = gamepad_backend
        self.mode = "hybrid" if gamepad_backend else keyboard_backend.mode

    def execute(self, action: dict):
        action_type = action.get("type")
        if action_type in {"gamepad_button", "move_left_stick"} and self.gamepad_backend:
            return self.gamepad_backend.execute(action)
        return self.keyboard_backend.execute(action)

    def capabilities(self):
        return {
            "keyboard": True,
            "gamepad": self.gamepad_backend is not None,
            "mode": self.mode,
        }


class NullInputBackend:
    mode = "null"

    def execute(self, action: dict):
        return False

    def capabilities(self):
        return {"keyboard": False, "gamepad": False, "mode": self.mode}


def get_backend():
    try:
        keyboard = WindowsKeyboardBackend()
    except Exception:
        keyboard = None

    try:
        gamepad = VirtualGamepadBackend()
    except Exception:
        gamepad = None

    if keyboard:
        return HybridBackend(keyboard, gamepad)
    return NullInputBackend()
