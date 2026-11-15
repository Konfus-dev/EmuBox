"""Typing into the app in front, as a keyboard of our own.

    typer = Typer()
    typer.text("Hello!")       typer.key("enter")

The on-screen keyboard and the phone keyboard type through this. It is a real
(virtual) keyboard as far as the system can tell: each key goes down and comes
up again, in order. The `wtype` tool, used before, makes a keyboard for one word
and takes it away at once; some apps then never see a key come back up, and it
repeats for ever (a terminal filling with one letter) or a modifier stays held
(every later key ignored). wtype is still what types a character this keyboard
has no key for, and everything when the system's key layout is not the US one.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

CONF = Path("/userdata/system/batocera.conf")
PLAIN = "abcdefghijklmnopqrstuvwxyz1234567890"
# On a US layout: the character -> (the key's name, whether Shift is held).
US = {c: (f"KEY_{c.upper()}", False) for c in PLAIN}
US.update({c.upper(): (f"KEY_{c.upper()}", True) for c in PLAIN[:26]})
for _plain, _shifted, _key in (("1", "!", "1"), ("2", "@", "2"), ("3", "#", "3"), ("4", "$", "4"), ("5", "%", "5"),
                               ("6", "^", "6"), ("7", "&", "7"), ("8", "*", "8"), ("9", "(", "9"), ("0", ")", "0"),
                               ("-", "_", "MINUS"), ("=", "+", "EQUAL"), ("[", "{", "LEFTBRACE"), ("]", "}", "RIGHTBRACE"),
                               ("\\", "|", "BACKSLASH"), (";", ":", "SEMICOLON"), ("'", '"', "APOSTROPHE"),
                               ("`", "~", "GRAVE"), (",", "<", "COMMA"), (".", ">", "DOT"), ("/", "?", "SLASH")):
    US[_plain], US[_shifted] = (f"KEY_{_key}", False), (f"KEY_{_key}", True)
US[" "] = ("KEY_SPACE", False)
NAMED = {"enter": "KEY_ENTER", "backspace": "KEY_BACKSPACE", "tab": "KEY_TAB", "space": "KEY_SPACE",
         "left": "KEY_LEFT", "right": "KEY_RIGHT"}
WTYPE_NAMES = {"enter": "Return", "backspace": "BackSpace", "tab": "Tab", "space": "space", "left": "Left", "right": "Right"}


def us_layout(conf: Path = CONF) -> bool:
    """True when the system's keys are laid out the US way (Batocera's default), so that
    pressing the key marked Q types a q."""
    try:
        for line in conf.read_text(errors="replace").splitlines():
            if line.startswith("system.kblayout="):
                return line.split("=", 1)[1].strip().lower() in ("", "us")
    except OSError:
        pass
    return True


class Typer:
    def __init__(self, own_keyboard: bool | None = None, device=None, run=subprocess.run, pause: float = 0.004):
        self.run, self.pause = run, pause
        self.device = device
        if device is None and (us_layout() if own_keyboard is None else own_keyboard):
            try:
                from evdev import UInput, ecodes
                codes = sorted({ecodes.ecodes[name] for name, _shift in US.values()} |
                               {ecodes.ecodes[name] for name in NAMED.values()} | {ecodes.KEY_LEFTSHIFT})
                self.device = UInput({ecodes.EV_KEY: codes}, name="EmuBox keyboard")
                time.sleep(0.4)   # the system needs a moment to notice a new keyboard; keys sent sooner are lost
            except Exception:   # noqa: BLE001  (no evdev, no access): the old way still types
                self.device = None

    def _tap(self, name: str, shift: bool = False) -> None:
        from evdev import ecodes
        steps = [(ecodes.KEY_LEFTSHIFT, 1)] if shift else []
        steps += [(ecodes.ecodes[name], 1), (ecodes.ecodes[name], 0)]
        steps += [(ecodes.KEY_LEFTSHIFT, 0)] if shift else []
        for code, value in steps:
            self.device.write(ecodes.EV_KEY, code, value)
            self.device.syn()
            time.sleep(self.pause)

    def _wtype(self, *words: str) -> None:
        try:
            self.run(["wtype", *words], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    def text(self, words: str) -> None:
        for character in words:
            if self.device is not None and character in US:
                self._tap(*US[character])
            else:
                self._wtype("--", character)

    def key(self, name: str) -> None:
        """A named key: enter, backspace, tab, space, left, right."""
        if name not in NAMED:
            return
        if self.device is not None:
            self._tap(NAMED[name])
        else:
            self._wtype("-k", WTYPE_NAMES[name])

    def close(self) -> None:
        if self.device is not None:
            try:
                self.device.close()
            except OSError:
                pass
            self.device = None
