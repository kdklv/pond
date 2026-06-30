"""Shared on-screen overlay style — the ASS "design system".

PondTV renders all UI as ASS subtitle events through mpv's ``osd-overlay`` on a
fixed 1920×1080 canvas. There is **one font, one size**; hierarchy comes from
colour and letter-spacing (``TRACK`` for tracked uppercase labels, ``TIGHT`` for
titles), plus a crisp 2px black outline for legibility over any video frame.

This module owns the constants and the small pure helpers every overlay screen
(the playback OSD, the idle/insert screens, and the browser) builds on. Keeping
them here lets the browser render without importing the manager (no cycle), and
keeps the visual language in one place — the warm monochrome palette and the
"editorial via tracking" rule live or die here.

ASS colour codes are ``&HBBGGRR&`` (note the reversed byte order vs. CSS).
"""

from __future__ import annotations

OV_FONT = "DejaVu Sans Mono"
OV_FS = 40                       # single type size on the 1920x1080 canvas
OV_X = 130                       # left margin
BAR_CELLS = 34                   # progress bar width, in mono cells

# Warm monochrome palette (off-white primary, muted gray secondary, dark track).
C_PRIMARY = r"{\c&HE3EAED&}"     # #EDEAE3 warm off-white — active text / fill
C_DIM = r"{\c&H848C8C&}"         # #8C8C84 muted gray — labels / secondary
C_TRACK = r"{\c&H464A4A&}"       # #4A4A46 — empty progress track

TRACK = r"{\fsp7}"               # tracked spacing for uppercase labels
TIGHT = r"{\fsp0}"               # normal spacing


def fmt_time(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def ass_escape(text: str) -> str:
    # Keep user filenames from breaking ASS markup.
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def bar(frac: float) -> str:
    frac = min(1.0, max(0.0, frac))
    filled = int(round(frac * BAR_CELLS))
    return f"{C_PRIMARY}{'█' * filled}{C_TRACK}{'░' * (BAR_CELLS - filled)}"


def style(an: int = 7, x: int = OV_X, y: int = 690) -> str:
    """Shared ASS preamble: the one font, the one size, a crisp legibility
    outline, anchored at (x, y)."""
    return (
        f"{{\\an{an}\\pos({x},{y})\\fn{OV_FONT}\\fs{OV_FS}\\b0"
        r"\bord2\3c&H000000&\shad0}"
    )
