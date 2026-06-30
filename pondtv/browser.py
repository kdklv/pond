"""The channel / file browser — a drill-down overlay rendered as ASS.

Two single-pane views, one screen at a time (the editorial call: one focused
list with real whitespace, not a cramped two-column grid):

* ``channels`` — every channel with a ``seen/total`` count; ``→`` drills in.
* ``episodes`` — the videos of the selected channel with a ``·`` seen mark;
  ``→`` plays, ``←`` returns to the channel list.

Rendering is **pure**: :func:`render_browser` takes the browser state and the
watch-state and returns an ASS string for ``osd-overlay``. The manager owns the
mutable cursor/top indices (under its lock) and calls this to redraw. That split
keeps the visual language testable without a manager or a Pi.

Visual system (see :mod:`pondtv.overlay`): one mono font, one size; hierarchy
via colour and tracking. The cursor row is the only bright line; everything else
is muted. ``·`` marks seen videos, ``seen/total`` marks channel progress — so
"what's left to watch" is scannable at a glance.
"""

from __future__ import annotations

from .channels import Channel
from .overlay import C_DIM, C_PRIMARY, TRACK, TIGHT, OV_X, ass_escape, style
from .state import State

BROWSER_ROWS = 12          # visible rows per pane; rest reached by scrolling
CH_NAME_WIDTH = 46         # channel name column (mono cells)
EP_NAME_WIDTH = 58         # episode name column (wider — no count suffix)
COUNT_WIDTH = 6            # right-aligned "seen/total" column


def scroll_to(cursor: int, top: int, n: int, rows: int) -> int:
    """New viewport top so ``cursor`` stays visible, last page kept full.

    Returns 0 when the whole list (``n``) fits in ``rows`` — no scrolling needed.
    """
    if n <= rows:
        return 0
    if cursor < top:
        top = cursor
    elif cursor > top + rows - 1:
        top = cursor - rows + 1
    top = min(top, n - rows)  # don't float the last page up
    return max(top, 0)


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 1] + "…"


def _seen_count(state: State | None, channel: Channel) -> int:
    if state is None:
        return 0
    return sum(1 for v in channel.videos if state.is_seen(v))


def _row(text: str, cursor: bool, *, dim_suffix: str = "") -> str:
    """One list row: bright ``▸``+title if cursor, muted otherwise.

    ``dim_suffix`` (e.g. the ``seen/total`` count) is always muted — it's meta,
    not the selection.
    """
    color = C_PRIMARY if cursor else C_DIM
    marker = "▸" if cursor else " "
    return f"{color}{marker} {text}{dim_suffix}"


def render_browser(
    mode: str,
    channels: list[Channel],
    ch_cursor: int,
    ch_top: int,
    ep_cursor: int,
    ep_top: int,
    state: State | None,
    rows: int = BROWSER_ROWS,
) -> str:
    """Build the ASS overlay string for the current browser view.

    ``mode`` is ``"channels"`` or ``"episodes"``. Cursor/top indices are the
    manager's (already scrolled into view); this function only formats what fits
    in the viewport.
    """
    if mode == "channels":
        return _render_channels(channels, ch_cursor, ch_top, state, rows)
    return _render_episodes(channels, ch_cursor, ep_cursor, ep_top, state, rows)


def _header(body: str, *parts: str) -> str:
    sep = "   "
    return f"{C_DIM}{TRACK}{body}" + sep + sep.join(parts)


def _frame(header: str, row_lines: list[str], footer: str) -> str:
    """Assemble one ASS event: header, a fixed-height row block, footer.

    Always emits exactly ``BROWSER_ROWS`` row lines (blanks padding short lists)
    so the footer sits at a constant vertical position regardless of list length
    — the block height never jitters as you scroll. Tracking is reset to
    :data:`TIGHT` for the row block (titles/markers are filenames, not labels)
    and back to :data:`TRACK` for the footer.
    """
    pad = BROWSER_ROWS - len(row_lines)
    rows_block = "\\N".join(row_lines + [" "] * pad)
    return (
        style(an=7, x=OV_X, y=140)
        + f"{header}\\N\\N"
        + f"{TIGHT}{rows_block}\\N\\N"
        + f"{C_DIM}{TRACK}{footer}"
    )


def _render_channels(
    channels: list[Channel],
    ch_cursor: int,
    ch_top: int,
    state: State | None,
    rows: int,
) -> str:
    n = len(channels)
    header = _header("BROWSE", f"{n} CHANNEL{n and 'S' or ''}")
    footer = "↑↓ SELECT    → OPEN    B CLOSE"

    lines: list[str] = []
    for i in range(rows):
        idx = ch_top + i
        if idx >= n:
            break
        ch = channels[idx]
        seen = _seen_count(state, ch)
        total = len(ch.videos)
        done = total > 0 and seen == total
        dot = "·" if done else " "
        name = ass_escape(_truncate(ch.name, CH_NAME_WIDTH)).ljust(CH_NAME_WIDTH)
        count = f"{seen}/{total}".rjust(COUNT_WIDTH)
        cur = idx == ch_cursor
        lines.append(_row(f"{name}   {C_DIM}{dot} ", cur, dim_suffix=f"  {C_DIM}{count}"))
    return _frame(header, lines, footer)


def _render_episodes(
    channels: list[Channel],
    ch_cursor: int,
    ep_cursor: int,
    ep_top: int,
    state: State | None,
    rows: int,
) -> str:
    ch = channels[ch_cursor]
    videos = ch.videos
    n = len(videos)
    header = _header("BROWSE", ass_escape(ch.name.upper()), f"{n} EPISODE{n and 'S' or ''}")
    footer = "↑↓ SELECT    → PLAY    ← BACK    B CLOSE"

    lines: list[str] = []
    for i in range(rows):
        idx = ep_top + i
        if idx >= n:
            break
        rel = videos[idx]
        seen = bool(state and state.is_seen(rel))
        dot = "·" if seen else " "
        name = ass_escape(_truncate(_episode_label(rel), EP_NAME_WIDTH))
        cur = idx == ep_cursor
        lines.append(_row(f"{C_DIM}{dot} {name}", cur))
    return _frame(header, lines, footer)


def _episode_label(rel: str) -> str:
    """Clean human label for a video: drop the extension, keep the filename.

    The folder/channel name already titles the show; the episode label is the
    file's own name (``S01E02 - The Title``), which natural-sort already ordered
    for us. We only strip the container extension — release-junk prefixes are
    the user's problem, and stripping them aggressively loses real titles.
    """
    import os

    return os.path.splitext(os.path.basename(rel))[0]
