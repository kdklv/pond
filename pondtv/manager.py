"""The brain: ties mpv, channels, state, keyboard, and the drive together.

This is the channel manager from the README — a thin coordinator, not a player.
It holds the current channel/video position, translates abstract
:class:`~pondtv.actions.Action`s into mpv commands, persists watch-state to the
USB, and reacts to the drive coming and going.

Threading: actions arrive on the keyboard thread, mpv events on the IPC reader
thread, mount/unmount on the drive poll thread, and a checkpoint timer ticks on
its own thread. All state mutation goes through ``self._lock`` so these can't
trip over each other.

Resume seek: after ``loadfile`` we can't seek until mpv has actually opened the
file, so we stash a pending position and apply it on the next
``playback-restart`` event.
"""

from __future__ import annotations

import random
import threading
import time
from pathlib import Path

from .actions import Action
from .channels import Channel, build_channels
from .input_kbd import KeyboardInput
from .drive import DriveManager
from .mpv_ipc import MpvIPC, launch_mpv
from .state import State, is_smart_seen

CHECKPOINT_SECONDS = 30  # how often to persist playback position while playing
SEEK_SECONDS = 10        # ←/→ scrub step
OVERLAY_ID = 1           # osd-overlay slot for our UI
RESUME_MIN_SECONDS = 60  # a video only "has a resume point" after ~1 min watched

# --- On-screen design system -------------------------------------------------
# One font, one size, everywhere. Hierarchy comes from colour, spacing, and
# letter-tracking — never size. Warm-monochrome inverted for a dark screen.
OV_FONT = "DejaVu Sans Mono"
OV_FS = 40                       # the single type size, in a 1920x1080 canvas
OV_X = 130                       # left margin
BAR_CELLS = 34                   # progress bar width, in mono cells

# ASS colours are &HBBGGRR&.
C_PRIMARY = r"{\c&HE3EAED&}"     # #EDEAE3 warm off-white — active text / fill
C_DIM = r"{\c&H848C8C&}"         # #8C8C84 muted gray — labels / secondary
C_TRACK = r"{\c&H464A4A&}"       # #4A4A46 — empty progress track
TRACK = r"{\fsp7}"               # tracked spacing for uppercase labels
TIGHT = r"{\fsp0}"               # normal spacing

# Hold durations (seconds) for transient overlays.
HOLD_TITLE = 3.4
HOLD_FLASH = 1.6
HOLD_SEEK = 1.3


def _fmt_time(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _ass_escape(text: str) -> str:
    # Keep user filenames from breaking ASS markup.
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def _bar(frac: float) -> str:
    frac = min(1.0, max(0.0, frac))
    filled = int(round(frac * BAR_CELLS))
    return f"{C_PRIMARY}{'█' * filled}{C_TRACK}{'░' * (BAR_CELLS - filled)}"


def _style(an: int = 7, x: int = OV_X, y: int = 690) -> str:
    """Shared ASS preamble: the one font, the one size, a crisp legibility
    outline, anchored at (x, y)."""
    return (
        f"{{\\an{an}\\pos({x},{y})\\fn{OV_FONT}\\fs{OV_FS}\\b0"
        r"\bord2\3c&H000000&\shad0}"
    )


class Manager:
    def __init__(self, mountpoint: str = "/mnt/pondtv"):
        self.mountpoint = mountpoint
        self.mpv = MpvIPC()
        self._mpv_proc = None
        self._lock = threading.RLock()

        self.root: str | None = None          # mounted USB root, or None
        self.channels: list[Channel] = []
        self.state: State | None = None
        self.ch_idx = 0                        # current channel index
        self.vid_idx = 0                       # current video index within channel
        self._current_rel: str | None = None   # rel path of the playing video
        # Where to jump once the freshly-loaded file starts: ("abs", secs) to
        # resume, ("pct", percent) for trailer mode, or None to start at 0.
        self._pending_start: tuple[str, float] | None = None
        self.trailer_mode = False
        self._overlay_gen = 0  # bumped on every overlay change; guards auto-clear
        self._running = False

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._mpv_proc = launch_mpv()
        self.mpv.connect()
        self.mpv.observe_property("eof-reached", 1)
        self.mpv.on_event(self._on_mpv_event)
        self._show_idle()

        self.keyboard = KeyboardInput(self._on_action, grab=True)
        self.keyboard.start()

        self.drive = DriveManager(self._on_mount, self._on_unmount, self.mountpoint)
        self.drive.start()

        self._checkpoint = threading.Thread(target=self._checkpoint_loop, daemon=True)
        self._checkpoint.start()

    def stop(self) -> None:
        self._running = False
        with self._lock:
            self._save_progress()
        try:
            self.keyboard.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.drive.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.mpv.command("quit")
        except Exception:  # noqa: BLE001
            pass
        if self._mpv_proc is not None:
            try:
                self._mpv_proc.terminate()
                self._mpv_proc.wait(timeout=5)
            except Exception:  # noqa: BLE001
                self._mpv_proc.kill()

    def run_forever(self) -> None:
        try:
            while self._running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    # -- drive callbacks --------------------------------------------------

    def _on_mount(self, root: str) -> None:
        with self._lock:
            self.root = root
            self.channels = build_channels(root)
            self.state = State(root)
            if not self.channels:
                self._no_videos()
                return
            self.ch_idx = 0
            self.vid_idx = self._resume_index_for_channel(self.ch_idx)
            self._play_current(resume=True)

    def _no_videos(self) -> None:
        ass = (
            _style(an=5, x=960, y=540)
            + f"{C_PRIMARY}{TRACK}PONDTV\\N\\N{C_DIM}{TRACK}NO VIDEOS ON THIS DRIVE"
        )
        self._set_overlay(ass)

    def _on_unmount(self) -> None:
        with self._lock:
            self._save_progress()
            self.root = None
            self.channels = []
            self.state = None
            self._current_rel = None
            try:
                self.mpv.set_pause(True)
                self.mpv.command("stop")
            except Exception:  # noqa: BLE001
                pass
            self._show_idle()

    # -- playback ---------------------------------------------------------

    def _resume_index_for_channel(self, ch_idx: int) -> int:
        """Index of the channel's saved 'current video', else 0."""
        ch = self.channels[ch_idx]
        if self.state is not None:
            cur = self.state.get_channel_current(ch.path)
            if cur in ch.videos:
                return ch.videos.index(cur)
        return 0

    def _resume_point(self, rel: str) -> float | None:
        """Saved position to resume to, or None if the video is 'fresh'.

        A video only counts as having a resume point once it's been watched for
        ~1 minute (and isn't already marked seen) — so quickly shuffling past
        things doesn't litter resume points, and trailer mode can tell a fresh
        video from one you're partway through.
        """
        if self.state is None:
            return None
        if self.state.is_seen(rel):
            return None
        pos = self.state.resume_position(rel)
        return pos if pos and pos >= RESUME_MIN_SECONDS else None

    # -- on-screen overlay engine ----------------------------------------

    def _set_overlay(self, ass: str, hold: float | None = None) -> None:
        """Show ASS overlay text; if ``hold`` is set, auto-clear after it.

        Uses a generation counter so a transient overlay's timer never clears a
        newer one. command_async keeps this safe to call from any thread.
        """
        self._overlay_gen += 1
        gen = self._overlay_gen
        self.mpv.command_async("osd-overlay", OVERLAY_ID, "ass-events", ass, 0, 1920, 1080)
        if hold is not None:
            t = threading.Timer(hold, self._clear_overlay, kwargs={"gen": gen})
            t.daemon = True
            t.start()

    def _clear_overlay(self, gen: int | None = None) -> None:
        # A timer only clears if nothing newer has been shown since.
        if gen is not None and gen != self._overlay_gen:
            return
        self._overlay_gen += 1
        self.mpv.command_async("osd-overlay", OVERLAY_ID, "none", "")

    def _channel_meta(self) -> tuple[str, str]:
        """(uppercase label line, clean title) for the current channel/video.

        The channel folder is the clean human name — far nicer than the raw
        release-junk filename — so we title with it and add EP n/N for series.
        """
        ch = self.channels[self.ch_idx]
        category = ch.path.split("/", 1)[0]
        n = len(ch.videos)
        parts = [] if category.lower() == ch.name.lower() else [category.upper()]
        if n > 1:
            parts.append(f"EP {self.vid_idx + 1}/{n}")
        if self.trailer_mode:
            parts.append("TRAILER")
        return "   ".join(parts), ch.name

    # -- overlay states ---------------------------------------------------

    def _show_idle(self) -> None:
        ass = (
            _style(an=5, x=960, y=540)
            + f"{C_PRIMARY}{TRACK}PONDTV\\N\\N"
            + f"{C_DIM}{TRACK}NO DRIVE DETECTED\\N"
            + f"{C_DIM}{TRACK}INSERT A USB DRIVE TO BEGIN"
        )
        self._set_overlay(ass)

    def _show_title(self) -> None:
        """Brief channel/title card on a change."""
        meta, title = self._channel_meta()
        head = f"{C_DIM}{TRACK}{_ass_escape(meta)}\\N" if meta else ""
        ass = _style(y=830) + head + f"{C_PRIMARY}{TIGHT}{_ass_escape(title)}"
        self._set_overlay(ass, hold=HOLD_TITLE)

    def _show_seek(self) -> None:
        """Transient progress readout while scrubbing during playback."""
        pos, dur = self._pos_dur()
        frac = (pos / dur) if dur else 0.0
        ass = (
            _style(y=860)
            + f"{C_DIM}{TIGHT}{_fmt_time(pos)}   {_bar(frac)}   {C_DIM}{_fmt_time(dur)}"
        )
        self._set_overlay(ass, hold=HOLD_SEEK)

    def _show_pause(self) -> None:
        """Persistent pause UI: label, title, time + progress, controls."""
        meta, title = self._channel_meta()
        label = f"PAUSED   {meta}".rstrip()
        pos, dur = self._pos_dur()
        frac = (pos / dur) if dur else 0.0
        ass = (
            _style(y=690)
            + f"{C_DIM}{TRACK}{_ass_escape(label)}\\N"
            + f"{C_PRIMARY}{TIGHT}{_ass_escape(title)}\\N\\N"
            + f"{C_DIM}{TIGHT}{_fmt_time(pos)}   {_bar(frac)}   {C_DIM}{_fmt_time(dur)}\\N\\N"
            + f"{C_DIM}{TRACK}←→ SEEK    A/D EPISODE    ↑↓ CHANNEL    SPACE PLAY"
        )
        self._set_overlay(ass)

    def _flash(self, text: str) -> None:
        """One-line transient status, e.g. RESTART / SEEN / TRAILER ON."""
        ass = _style(y=880) + f"{C_DIM}{TRACK}{_ass_escape(text.upper())}"
        self._set_overlay(ass, hold=HOLD_FLASH)

    def _pos_dur(self) -> tuple[float, float]:
        try:
            return (self.mpv.get_property("time-pos") or 0.0,
                    self.mpv.get_property("duration") or 0.0)
        except Exception:  # noqa: BLE001
            return 0.0, 0.0

    def _play_current(self, resume: bool = True, trailer: bool = False) -> None:
        """Load + play the video at (ch_idx, vid_idx). Caller holds the lock."""
        if not self.channels:
            return
        ch = self.channels[self.ch_idx]
        rel = ch.videos[self.vid_idx]
        abspath = str(Path(self.root) / rel)

        self._current_rel = rel
        resume_pos = self._resume_point(rel)
        if trailer and resume_pos is None:
            # Trailer mode only applies to "fresh" videos with no resume point:
            # jump into a random 5–20% spot, like flipping past a show already
            # in progress. A video you've actually been watching resumes instead.
            self._pending_start = ("pct", random.uniform(5.0, 20.0))
        elif resume and resume_pos is not None:
            self._pending_start = ("abs", resume_pos)
        else:
            self._pending_start = None

        self._clear_overlay()
        self.mpv.loadfile(abspath)
        self.mpv.set_pause(False)
        if self.state is not None:
            self.state.set_channel_current(ch.path, rel)
            self._save(safe=True)
        self._show_title()

    def _save_progress(self) -> None:
        """Read mpv's current position into state for the playing video."""
        if self.state is None or self._current_rel is None:
            return
        try:
            pos = self.mpv.get_property("time-pos")
            dur = self.mpv.get_property("duration")
        except Exception:  # noqa: BLE001 - mpv may be between files
            return
        if pos is None:
            return
        self.state.update_video(self._current_rel, position=float(pos),
                                duration=float(dur) if dur else 0.0)
        self._save(safe=True)

    def _save(self, safe: bool = False) -> None:
        if self.state is None:
            return
        try:
            self.state.save()
        except OSError:
            if not safe:
                raise  # a flaky drive must not crash playback

    def _advance(self, delta: int, save_current: bool = True) -> None:
        """Move within the current channel by delta videos (wraps). Holds lock."""
        if not self.channels:
            return
        if save_current:
            self._save_progress()
        n = len(self.channels[self.ch_idx].videos)
        self.vid_idx = (self.vid_idx + delta) % n
        self._play_current(resume=True)

    def _change_channel(self, delta: int) -> None:
        if not self.channels:
            return
        self._save_progress()
        self.ch_idx = (self.ch_idx + delta) % len(self.channels)
        self.vid_idx = self._resume_index_for_channel(self.ch_idx)
        self._play_current(resume=not self.trailer_mode, trailer=self.trailer_mode)

    # -- mpv events -------------------------------------------------------

    def _on_mpv_event(self, e: dict) -> None:
        ev = e.get("event")
        if ev == "playback-restart" and self._pending_start is not None:
            kind, val = self._pending_start
            self._pending_start = None
            # NB: we're on the IPC reader thread here — must not block, so use
            # the fire-and-forget command (a blocking one would deadlock).
            if kind == "abs":
                self.mpv.command_async("seek", val, "absolute")
            else:
                self.mpv.command_async("seek", val, "absolute-percent")
        elif ev == "property-change" and e.get("name") == "eof-reached" and e.get("data"):
            self._on_eof()

    def _on_eof(self) -> None:
        with self._lock:
            if not self.channels or self._current_rel is None:
                return
            # Reaching the end always counts as seen; advance to the next video.
            if self.state is not None:
                self.state.mark_seen(self._current_rel)
                self._save(safe=True)
            self._advance(+1, save_current=False)

    # -- input ------------------------------------------------------------

    def _on_action(self, action: Action, repeat: bool = False) -> None:
      try:
        with self._lock:
            if action is Action.QUIT:
                self._running = False
                return
            if not self.channels:
                self._show_idle()
                return
            if action in (Action.SEEK_BACK, Action.SEEK_FWD):
                self._seek(SEEK_SECONDS if action is Action.SEEK_FWD else -SEEK_SECONDS)
                return
            if action is Action.PLAY_PAUSE:
                self._toggle_pause()
            elif action is Action.NEXT:
                self._advance(+1)
            elif action is Action.PREV:
                self._advance(-1)
            elif action is Action.CHANNEL_UP:
                self._change_channel(+1)
            elif action is Action.CHANNEL_DOWN:
                self._change_channel(-1)
            elif action is Action.RESTART:
                self.mpv.restart()
                self._flash("RESTART")
            elif action is Action.MARK_SEEN:
                if self.state is not None and self._current_rel is not None:
                    self.state.mark_seen(self._current_rel)
                    self._save(safe=True)
                self._advance(+1, save_current=False)
            elif action is Action.BROWSE:
                self._flash("BROWSER — SOON")
            elif action is Action.TOGGLE_TRAILER:
                self.trailer_mode = not self.trailer_mode
                self._flash(f"TRAILER {'ON' if self.trailer_mode else 'OFF'}")
            elif action is Action.SLEEP:
                self._flash("SLEEP — SOON")
      except Exception:  # noqa: BLE001 - one bad command must not break input
        import traceback
        traceback.print_exc()

    def _toggle_pause(self) -> None:
        try:
            paused = bool(self.mpv.get_property("pause"))
        except Exception:  # noqa: BLE001
            paused = False
        now_paused = not paused
        self.mpv.set_pause(now_paused)
        if now_paused:
            self._save_progress()   # good moment to checkpoint
            self._show_pause()      # show the controls/time/progress UI
        else:
            self._clear_overlay()

    def _seek(self, delta: float) -> None:
        """Relative scrub; refreshes the pause UI, or a transient bar if playing."""
        # Fire-and-forget: a seek can fail (not yet seekable, past EOF) and that
        # must not raise. mpv updates time-pos shortly after; the overlay reads
        # it on the next refresh.
        self.mpv.command_async("seek", delta, "relative")
        try:
            paused = bool(self.mpv.get_property("pause"))
        except Exception:  # noqa: BLE001
            paused = False
        if paused:
            self._show_pause()
        else:
            self._show_seek()

    # -- periodic checkpoint ---------------------------------------------

    def _checkpoint_loop(self) -> None:
        while self._running:
            time.sleep(CHECKPOINT_SECONDS)
            with self._lock:
                try:
                    if not bool(self.mpv.get_property("pause")):
                        self._save_progress()
                except Exception:  # noqa: BLE001
                    pass
