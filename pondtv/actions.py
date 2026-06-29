"""The hardware-agnostic action vocabulary.

The core (manager) only ever sees these abstract actions — never key codes,
CEC commands, or GPIO pins. Input drivers (the v1 keyboard, a future HDMI-CEC
or GPIO knob) translate their hardware events into ``Action`` values, so a new
front-end can be added without touching the core. See README → "Input is
pluggable".
"""

from __future__ import annotations

from enum import Enum, auto


class Action(Enum):
    PLAY_PAUSE = auto()     # Space / OK — toggle pause
    PREV = auto()           # A — previous video within the current channel
    NEXT = auto()           # D — next video within the current channel
    SEEK_BACK = auto()      # ← scrub back 10s (hold to rewind)
    SEEK_FWD = auto()       # → scrub forward 10s (hold to fast-forward)
    CHANNEL_UP = auto()     # ↑ surf to the next channel
    CHANNEL_DOWN = auto()   # ↓ surf to the previous channel
    RESTART = auto()        # Backspace — restart the current video
    MARK_SEEN = auto()      # S — mark seen and skip to next
    BROWSE = auto()         # B — open the channel / file browser
    SLEEP = auto()          # start the shut-off timer
    TOGGLE_TRAILER = auto()  # trailer mode: channel changes start at a random offset
    QUIT = auto()           # dev/maintenance — exit the app
