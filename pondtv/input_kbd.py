"""evdev keyboard input driver → abstract :class:`Action`.

Reads keyboards from ``/dev/input`` directly (no X11/desktop), so it works on a
headless console tty — which is why we use ``evdev`` and not ``pynput`` (pynput
silently needs a display). A USB keyboard often exposes several event devices
(main keys, consumer/media keys, system/power keys); we read from all of them
so keys like Sleep land regardless of which node carries them.

The driver runs a background thread, translates key-down events to actions via
:data:`KEYMAP`, and hands each action to a callback. Hardware stays behind the
:class:`Action` abstraction — the manager never sees a key code.
"""

from __future__ import annotations

import selectors
import threading
from typing import Callable

import evdev
from evdev import ecodes

from .actions import Action

# Key code → action. ←/→ scrub (held = fast-forward), A/D step episodes, ↑/↓
# surf channels. Enter doubles as OK/play-pause; Esc/Q are dev conveniences.
KEYMAP: dict[int, Action] = {
    ecodes.KEY_SPACE: Action.PLAY_PAUSE,
    ecodes.KEY_ENTER: Action.PLAY_PAUSE,
    ecodes.KEY_KPENTER: Action.PLAY_PAUSE,
    ecodes.KEY_LEFT: Action.SEEK_BACK,
    ecodes.KEY_RIGHT: Action.SEEK_FWD,
    ecodes.KEY_A: Action.PREV,
    ecodes.KEY_D: Action.NEXT,
    ecodes.KEY_UP: Action.CHANNEL_UP,
    ecodes.KEY_DOWN: Action.CHANNEL_DOWN,
    ecodes.KEY_BACKSPACE: Action.RESTART,
    ecodes.KEY_S: Action.MARK_SEEN,
    ecodes.KEY_B: Action.BROWSE,
    ecodes.KEY_T: Action.TOGGLE_TRAILER,
    ecodes.KEY_SLEEP: Action.SLEEP,
    ecodes.KEY_POWER: Action.SLEEP,
    ecodes.KEY_ESC: Action.QUIT,
    ecodes.KEY_Q: Action.QUIT,
}

# Held keys (autorepeat) only fire these — scrubbing should repeat while held,
# but you don't want to surf 30 channels by leaning on the arrow key.
REPEATABLE = {Action.SEEK_BACK, Action.SEEK_FWD}


def find_keyboards() -> list[evdev.InputDevice]:
    """All input devices that can emit at least one key we care about."""
    wanted = set(KEYMAP)
    devices = []
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except OSError:
            continue
        keys = set(dev.capabilities().get(ecodes.EV_KEY, []))
        if keys & wanted:
            devices.append(dev)
    return devices


class KeyboardInput:
    """Background evdev reader that dispatches abstract actions to a callback."""

    def __init__(self, callback: Callable[[Action, bool], None], grab: bool = False):
        self.callback = callback
        self.grab = grab  # EVIOCGRAB: keep keystrokes out of the console tty
        self.devices = find_keyboards()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.devices:
            raise RuntimeError("no keyboard devices found under /dev/input")
        if self.grab:
            for dev in self.devices:
                try:
                    dev.grab()
                except OSError:
                    pass
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        sel = selectors.DefaultSelector()
        for dev in self.devices:
            sel.register(dev, selectors.EVENT_READ)
        while self._running:
            for key, _ in sel.select(timeout=0.5):
                dev = key.fileobj
                try:
                    for event in dev.read():
                        # 1 = key-down, 2 = autorepeat (held), 0 = release.
                        if event.type != ecodes.EV_KEY or event.value not in (1, 2):
                            continue
                        action = KEYMAP.get(event.code)
                        if action is None:
                            continue
                        repeat = event.value == 2
                        if repeat and action not in REPEATABLE:
                            continue  # don't let a held key spam non-scrub actions
                        try:
                            self.callback(action, repeat)
                        except Exception:  # noqa: BLE001 - a handler error must
                            import traceback  # never kill input handling
                            traceback.print_exc()
                except OSError:
                    pass  # device unplugged mid-read; ignore

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self.grab:
            for dev in self.devices:
                try:
                    dev.ungrab()
                except OSError:
                    pass


if __name__ == "__main__":
    # Step-4 demo: print each key press. Mapped keys show their Action; any
    # other key shows its raw name (to confirm the Pi sees the keyboard at all).
    # Press Esc or Q to quit.
    import selectors as _sel
    import threading as _t

    devices = find_keyboards()
    print("listening on:", flush=True)
    for d in devices:
        print(f"  {d.path}  {d.name!r}", flush=True)
    print("\npress keys (Space, arrows, Backspace, S, B, Sleep); Esc/Q to quit\n", flush=True)

    done = _t.Event()
    sel = _sel.DefaultSelector()
    for d in devices:
        sel.register(d, _sel.EVENT_READ)

    while not done.is_set():
        for key, _ in sel.select(timeout=0.5):
            dev = key.fileobj
            try:
                for event in dev.read():
                    if event.type != ecodes.EV_KEY or event.value != 1:
                        continue
                    keyname = ecodes.KEY.get(event.code, event.code)
                    action = KEYMAP.get(event.code)
                    label = action.name if action else f"(unmapped {keyname})"
                    print(f"  key {keyname} -> {label}", flush=True)
                    if action is Action.QUIT:
                        done.set()
            except OSError:
                pass
    print("stopped", flush=True)
