#!/usr/bin/env python3
"""vinylcast screen manager.

Turns the touchscreen OFF when nothing is playing, and back ON when audio starts
or the screen is tapped. Meant to run inside the labwc/Wayland session (so it can
reach the compositor via wlopm) — launch it from labwc autostart.

  screen ON  ⟺  something is playing  OR  a tap happened within WAKE_SECONDS
  screen OFF ⟺  otherwise

Taps are read straight from the kernel via evdev, so they wake the panel even while
it's powered off (the touchscreen input is independent of the display backlight).

Deps: python3-evdev, wlopm. Env: WAYLAND_DISPLAY + XDG_RUNTIME_DIR (set by the
labwc session when launched from autostart).
"""
import json
import subprocess
import threading
import time
import urllib.request

WAKE_SECONDS = 45                       # stay awake this long after a tap
POLL = 2.0                              # how often to re-evaluate
STATE_URL = "http://localhost:8080/state"

_last_activity = time.monotonic()       # start awake so boot shows the UI briefly
_lock = threading.Lock()


def _monitor_input() -> None:
    """Bump _last_activity on any input event (kernel-level, works while display off)."""
    global _last_activity
    import evdev
    from selectors import DefaultSelector, EVENT_READ

    sel = DefaultSelector()
    for path in evdev.list_devices():
        try:
            sel.register(evdev.InputDevice(path), EVENT_READ)
        except Exception:
            pass
    while True:
        for key, _ in sel.select():
            try:
                for _ev in key.fileobj.read():   # draining events == there was activity
                    with _lock:
                        _last_activity = time.monotonic()
            except Exception:
                pass


def _is_playing() -> bool:
    try:
        with urllib.request.urlopen(STATE_URL, timeout=2) as r:
            return bool(json.load(r).get("playing"))
    except Exception:
        return False


def _set_display(on: bool) -> None:
    subprocess.run(["wlopm", "--on" if on else "--off", "*"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    threading.Thread(target=_monitor_input, daemon=True).start()
    on = True
    _set_display(True)
    while True:
        with _lock:
            idle = time.monotonic() - _last_activity
        awake = _is_playing() or idle < WAKE_SECONDS
        if awake != on:
            _set_display(awake)
            on = awake
        time.sleep(POLL)


if __name__ == "__main__":
    main()
