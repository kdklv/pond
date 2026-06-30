"""The brain: ties mpv, channels, state, keyboard, and the drive together.

This is the channel manager from the README — a thin coordinator, not a player.
It holds the current channel/video position, translates abstract
:class:`~pondtv.actions.Action`s into mpv commands, persists watch-state to the
USB, and reacts to the drive coming and going.

Threading model (the invariant that keeps it deadlock-free):

* Actions arrive on the keyboard thread, mpv events on the IPC reader thread,
  mount/unmount on the drive poll thread, and timers/checkpoints on their own
  threads. All state mutation goes through ``self._lock``.
* **No blocking IPC call or fsync is ever made while holding ``self._lock``.**
  The reader thread needs ``self._lock`` to dispatch an end-of-file, so a
  blocking ``command()`` under the lock could never get its reply (the reader is
  the only thing that reads replies) → deadlock. Therefore the manager *never*
  makes a blocking mpv call: it issues commands fire-and-forget via
  ``command_async`` and reads playback state from an **observed-property cache**
  (``self._props``) that the reader thread keeps fresh.
* Persistence (the fsync) runs on a dedicated **writer thread**; callers only
  flip an in-memory record and poke an event, so a slow/flaky drive can't freeze
  input or playback.

Resume seek: after ``loadfile`` we can't seek until mpv has actually opened the
file, so we stash a pending position and apply it on the next
``playback-restart`` event.
"""

from __future__ import annotations

import random
import threading
import time
import traceback
from pathlib import Path

from .actions import Action
from .browser import BROWSER_ROWS, render_browser, scroll_to
from .channels import Channel, build_channels
from .config import Config, load_drive_overrides
from .input_kbd import KeyboardInput
from .drive import DriveManager
from .mpv_ipc import MpvIPC, launch_mpv
from .overlay import (
    C_DIM,
    C_PRIMARY,
    C_TRACK,
    TIGHT,
    TRACK,
    OV_X,
    ass_escape,
    bar,
    fmt_time,
    style,
)
from .state import State

OVERLAY_ID = 1           # osd-overlay slot for our UI

# observe_property ids → the playback state we keep cached so we never have to
# make a blocking get_property call (see module docstring).
OBS_EOF = 1
OBS_TIMEPOS = 2
OBS_DURATION = 3
OBS_PAUSE = 4

# Hold durations (seconds) for transient overlays.
HOLD_TITLE = 3.4
HOLD_FLASH = 1.6
HOLD_SEEK = 1.3


class Manager:
    def __init__(self, config: Config | None = None):
        self._base_cfg = config or Config()
        self.cfg = self._base_cfg            # re-merged per drive on mount
        self.mountpoint = self.cfg.mountpoint
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
        self.trailer_mode = self.cfg.trailer_default
        self._overlay_gen = 0  # bumped on every overlay change; guards auto-clear
        # Browser overlay state. ``_browser_mode`` is None when closed, else
        # "channels" or "episodes" (the two drill-down panes). Cursors/tops are
        # scroll offsets kept inside the lock; rendering is done by browser.py.
        self._browser_mode: str | None = None
        self._br_ch_cursor = 0
        self._br_ch_top = 0
        self._br_ep_cursor = 0
        self._br_ep_top = 0
        self._browser_was_paused = False  # pause state captured on open, restored on close

        # Latest values of observed mpv properties, kept fresh by the reader
        # thread so we never block on a get_property. Read via _prop().
        self._props: dict[str, object] = {}
        self._running = False

        # Threads/components created in start(); declared here so stop() and the
        # watchdog can safely reference them even if start() failed partway.
        self.keyboard: KeyboardInput | None = None
        self.drive: DriveManager | None = None
        self._checkpoint: threading.Thread | None = None
        self._writer: threading.Thread | None = None
        self._watchdog: threading.Thread | None = None
        self._save_event = threading.Event()

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        self._running = True
        # Persistence first, so any early save has somewhere to go.
        self._writer = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer.start()

        self._mpv_proc = launch_mpv()
        self._connect_mpv()
        self._show_idle()

        # Soft-fail: a missing keyboard must not down the appliance — the input
        # driver starts anyway and watches for one to be plugged in.
        self.keyboard = KeyboardInput(
            self._on_action, grab=True, rescan_seconds=self.cfg.keyboard_rescan_seconds
        )
        try:
            self.keyboard.start()
        except Exception:  # noqa: BLE001 - never let input bring-up kill startup
            traceback.print_exc()

        self.drive = DriveManager(
            self._on_mount, self._on_unmount, self.mountpoint, self.cfg.poll_interval
        )
        self.drive.start()

        self._checkpoint = threading.Thread(target=self._checkpoint_loop, daemon=True)
        self._checkpoint.start()
        self._watchdog = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog.start()

    def _connect_mpv(self) -> None:
        """(Re)connect the IPC client and (re)register observers + event hook."""
        self.mpv = MpvIPC()
        self.mpv.connect()
        self.mpv.observe_property("eof-reached", OBS_EOF)
        self.mpv.observe_property("time-pos", OBS_TIMEPOS)
        self.mpv.observe_property("duration", OBS_DURATION)
        self.mpv.observe_property("pause", OBS_PAUSE)
        self.mpv.on_event(self._on_mpv_event)

    def stop(self) -> None:
        self._running = False
        try:
            with self._lock:
                self._save_progress()  # capture final position into memory
        except Exception:  # noqa: BLE001
            pass
        # Wake the writer so it exits promptly, then flush once synchronously.
        self._save_event.set()
        if self._writer is not None:
            self._writer.join(timeout=2.0)
        self._persist()

        if self.keyboard is not None:
            try:
                self.keyboard.stop()
            except Exception:  # noqa: BLE001
                pass
        if self.drive is not None:
            try:
                self.drive.stop()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.mpv.command("quit")  # blocking, but we're on the main thread
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

    # -- mpv watchdog -----------------------------------------------------

    def _watchdog_loop(self) -> None:
        """If mpv dies (bad codec, OOM, crash), relaunch and resume the video."""
        while self._running:
            time.sleep(self.cfg.watchdog_seconds)
            if self._running and not self.mpv.is_connected():
                try:
                    self._reconnect_mpv()
                except Exception:  # noqa: BLE001 - retry on the next tick
                    traceback.print_exc()

    def _reconnect_mpv(self) -> None:
        if self._mpv_proc is not None:
            try:
                self._mpv_proc.kill()
            except Exception:  # noqa: BLE001
                pass
        self._mpv_proc = launch_mpv()
        self._connect_mpv()  # raises if mpv didn't come back; watchdog retries
        with self._lock:
            self._props.clear()
            self._pending_start = None
            self._browser_mode = None  # mpv restart wiped the overlay; drop browse state
            if self.channels:
                self._play_current(resume=True)  # resume from last saved position
            elif self.root is not None:
                self._no_videos()
            else:
                self._show_idle()

    # -- drive callbacks --------------------------------------------------

    def _on_mount(self, root: str) -> None:
        with self._lock:
            self.root = root
            # Per-drive config travels with the mixtape; re-merge from the base
            # each mount so a drive without one reverts to machine defaults.
            self.cfg = self._base_cfg.merged(load_drive_overrides(root))
            self.trailer_mode = self.cfg.trailer_default
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
            style(an=5, x=960, y=540)
            + f"{C_PRIMARY}{TRACK}PONDTV\\N\\N{C_DIM}{TRACK}NO VIDEOS ON THIS DRIVE"
        )
        self._set_overlay(ass)

    def _on_unmount(self) -> None:
        with self._lock:
            self._browser_mode = None  # drop out of the browser if it was open
            self._save_progress()
            self.root = None
            self.channels = []
            self.state = None
            self._current_rel = None
            self.mpv.set_property_async("pause", True)
            self.mpv.command_async("stop")
            self._show_idle()

    # -- playback ---------------------------------------------------------

    def _prop(self, name: str, default=None):
        """Latest observed value of an mpv property, or ``default`` if unknown.

        Lock-free: the reader thread writes single keys, we read single keys —
        the GIL makes each safe, and a slightly stale value only ever affects a
        transient overlay or a checkpoint position.
        """
        val = self._props.get(name)
        return default if val is None else val

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
        return pos if pos and pos >= self.cfg.resume_min_seconds else None

    # -- on-screen overlay engine ----------------------------------------

    def _set_overlay(self, ass: str, hold: float | None = None) -> None:
        """Show ASS overlay text; if ``hold`` is set, auto-clear after it.

        Uses a generation counter (guarded by the lock) so a transient overlay's
        timer never clears a newer one. command_async keeps this non-blocking and
        thus safe to call from any thread, including under the lock.
        """
        with self._lock:
            self._overlay_gen += 1
            gen = self._overlay_gen
        self.mpv.command_async("osd-overlay", OVERLAY_ID, "ass-events", ass, 0, 1920, 1080)
        if hold is not None:
            t = threading.Timer(hold, self._clear_overlay, kwargs={"gen": gen})
            t.daemon = True
            t.start()

    def _clear_overlay(self, gen: int | None = None) -> None:
        # A timer only clears if nothing newer has been shown since.
        with self._lock:
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
            style(an=5, x=960, y=540)
            + f"{C_PRIMARY}{TRACK}PONDTV\\N\\N"
            + f"{C_DIM}{TRACK}NO DRIVE DETECTED\\N"
            + f"{C_DIM}{TRACK}INSERT A USB DRIVE TO BEGIN"
        )
        self._set_overlay(ass)

    def _show_title(self) -> None:
        """Brief channel/title card on a change."""
        meta, title = self._channel_meta()
        head = f"{C_DIM}{TRACK}{ass_escape(meta)}\\N" if meta else ""
        ass = style(y=830) + head + f"{C_PRIMARY}{TIGHT}{ass_escape(title)}"
        self._set_overlay(ass, hold=HOLD_TITLE)

    def _show_seek(self) -> None:
        """Transient progress readout while scrubbing during playback."""
        pos, dur = self._pos_dur()
        frac = (pos / dur) if dur else 0.0
        ass = (
            style(y=860)
            + f"{C_DIM}{TIGHT}{fmt_time(pos)}   {bar(frac)}   {C_DIM}{fmt_time(dur)}"
        )
        self._set_overlay(ass, hold=HOLD_SEEK)

    def _show_pause(self) -> None:
        """Persistent pause UI: label, title, time + progress, controls."""
        meta, title = self._channel_meta()
        label = f"PAUSED   {meta}".rstrip()
        pos, dur = self._pos_dur()
        frac = (pos / dur) if dur else 0.0
        ass = (
            style(y=690)
            + f"{C_DIM}{TRACK}{ass_escape(label)}\\N"
            + f"{C_PRIMARY}{TIGHT}{ass_escape(title)}\\N\\N"
            + f"{C_DIM}{TIGHT}{fmt_time(pos)}   {bar(frac)}   {C_DIM}{fmt_time(dur)}\\N\\N"
            + f"{C_DIM}{TRACK}←→ SEEK    A/D EPISODE    ↑↓ CHANNEL    SPACE PLAY"
        )
        self._set_overlay(ass)

    def _flash(self, text: str) -> None:
        """One-line transient status, e.g. RESTART / SEEN / TRAILER ON."""
        ass = style(y=880) + f"{C_DIM}{TRACK}{ass_escape(text.upper())}"
        self._set_overlay(ass, hold=HOLD_FLASH)

    def _pos_dur(self) -> tuple[float, float]:
        return float(self._prop("time-pos", 0.0)), float(self._prop("duration", 0.0))

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
        # Fire-and-forget: we're frequently under the lock and sometimes on the
        # reader thread (EOF) — a blocking load/pause would deadlock.
        self.mpv.command_async("loadfile", abspath, "replace")
        self.mpv.set_property_async("pause", False)
        self._props["pause"] = False  # optimistic; the observer will confirm
        if self.state is not None:
            self.state.set_channel_current(ch.path, rel)
            self._request_save()
        self._show_title()

    # -- persistence (writer thread) -------------------------------------

    def _request_save(self) -> None:
        """Ask the writer thread to flush state. Non-blocking; coalesces."""
        self._save_event.set()

    def _writer_loop(self) -> None:
        """Owns every fsync. Callers only mutate memory + poke _save_event, so a
        stalled write on a browned-out drive can't freeze input or playback."""
        while self._running:
            if not self._save_event.wait(timeout=1.0):
                continue
            self._save_event.clear()
            self._persist()

    def _persist(self) -> None:
        # Snapshot under the lock (cheap), fsync outside it (potentially slow).
        with self._lock:
            st = self.state
            if st is None:
                return
            payload = st.serialize()
        try:
            st.write_payload(payload)
        except OSError:
            pass  # a flaky drive must not crash playback

    def _save_progress(self) -> None:
        """Record mpv's current position for the playing video (caller holds lock)."""
        if self.state is None or self._current_rel is None:
            return
        pos = self._prop("time-pos")
        if pos is None:
            return
        dur = self._prop("duration")
        self.state.update_video(
            self._current_rel, position=float(pos), duration=float(dur) if dur else 0.0
        )
        self._request_save()

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
        if ev == "property-change":
            name = e.get("name")
            if name == "eof-reached":
                if e.get("data"):
                    self._on_eof()
            else:
                # time-pos / duration / pause cache (lock-free single-key write).
                self._props[name] = e.get("data")
            return
        if ev == "playback-restart":
            # File is open and seekable now — apply any pending resume/trailer
            # jump. Grab it under the lock (it's written there), but issue the
            # seek async and *outside* the lock: we're on the reader thread, so a
            # blocking command would wait on a reply only we can read.
            with self._lock:
                pending = self._pending_start
                self._pending_start = None
            if pending is not None:
                kind, val = pending
                mode = "absolute" if kind == "abs" else "absolute-percent"
                self.mpv.command_async("seek", val, mode)

    def _on_eof(self) -> None:
        with self._lock:
            if not self.channels or self._current_rel is None:
                return
            # The browser pauses playback on open, so EOF shouldn't fire while
            # it's up; if a race delivers one anyway, ignore it rather than let
            # an auto-advance clobber the browse overlay.
            if self._browser_mode is not None:
                return
            # Reaching the end always counts as seen; advance to the next video.
            if self.state is not None:
                self.state.mark_seen(self._current_rel)
                self._request_save()
            self._advance(+1, save_current=False)

    # -- input ------------------------------------------------------------

    def _on_action(self, action: Action, repeat: bool = False) -> None:
        try:
            with self._lock:
                if action is Action.QUIT:
                    if self.cfg.allow_quit:
                        self._running = False
                    return
                # B toggles the browser open/closed. Opening requires a mounted
                # drive (no browsing the idle screen).
                if action is Action.BROWSE:
                    if self._browser_mode is not None:
                        self._close_browser(restore=True)
                    elif self.channels:
                        self._open_browser()
                    return
                # While open, the browser captures every navigation action; only
                # QUIT (above) leaks through. This keeps playback controls from
                # fighting the browse cursor.
                if self._browser_mode is not None:
                    self._on_browser_action(action)
                    return
                if not self.channels:
                    self._show_idle()
                    return
                if action in (Action.SEEK_BACK, Action.SEEK_FWD):
                    step = self.cfg.seek_seconds
                    self._seek(step if action is Action.SEEK_FWD else -step)
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
                    self.mpv.command_async("seek", 0, "absolute")
                    self._flash("RESTART")
                elif action is Action.MARK_SEEN:
                    if self.state is not None and self._current_rel is not None:
                        self.state.mark_seen(self._current_rel)
                        self._request_save()
                    self._advance(+1, save_current=False)
                elif action is Action.TOGGLE_TRAILER:
                    self.trailer_mode = not self.trailer_mode
                    self._flash(f"TRAILER {'ON' if self.trailer_mode else 'OFF'}")
                elif action is Action.SLEEP:
                    self._flash("SLEEP — SOON")
        except Exception:  # noqa: BLE001 - one bad command must not break input
            traceback.print_exc()

    def _toggle_pause(self) -> None:
        now_paused = not bool(self._prop("pause", False))
        self.mpv.set_property_async("pause", now_paused)
        self._props["pause"] = now_paused  # optimistic; the observer will confirm
        if now_paused:
            self._save_progress()   # good moment to checkpoint
            self._show_pause()      # show the controls/time/progress UI
        else:
            self._clear_overlay()

    def _seek(self, delta: float) -> None:
        """Relative scrub; refreshes the pause UI, or a transient bar if playing."""
        # Fire-and-forget: a seek can fail (not yet seekable, past EOF) and that
        # must not raise. mpv updates time-pos shortly after; the overlay reads
        # it from the cache on the next refresh.
        self.mpv.command_async("seek", delta, "relative")
        if bool(self._prop("pause", False)):
            self._show_pause()
        else:
            self._show_seek()

    # -- browser overlay --------------------------------------------------

    def _render_browser(self) -> None:
        """Redraw the browse overlay from the current cursor/top state."""
        if self._browser_mode is None:
            return
        ass = render_browser(
            self._browser_mode,
            self.channels,
            self._br_ch_cursor,
            self._br_ch_top,
            self._br_ep_cursor,
            self._br_ep_top,
            self.state,
        )
        self._set_overlay(ass)

    def _open_browser(self) -> None:
        """Enter the browser at the channel list, parked on the current channel.

        Playback is paused and the position checkpointed so the browser is a
        focused, frozen-frame mode; the prior pause state is restored on close.
        Caller holds the lock; ``self.channels`` is non-empty (checked upstream).
        """
        self._browser_mode = "channels"
        self._br_ch_cursor = self.ch_idx
        self._br_ch_top = scroll_to(
            self._br_ch_cursor, 0, len(self.channels), BROWSER_ROWS
        )
        self._br_ep_cursor = 0
        self._br_ep_top = 0
        self._browser_was_paused = bool(self._prop("pause", False))
        self._save_progress()
        self.mpv.set_property_async("pause", True)
        self._props["pause"] = True
        self._render_browser()

    def _close_browser(self, restore: bool = True) -> None:
        """Leave the browser. If ``restore``, put playback back as it was (play
        or pause); if not, the caller has already loaded a fresh video."""
        self._browser_mode = None
        if restore:
            self._restore_after_browser()

    def _restore_after_browser(self) -> None:
        was = self._browser_was_paused
        self.mpv.set_property_async("pause", was)
        self._props["pause"] = was
        if was:
            self._show_pause()
        else:
            self._clear_overlay()

    def _on_browser_action(self, action: Action) -> None:
        # ↑/↓ move the cursor in the active pane; →/D/Space drill in or play;
        # ←/A/Backspace go back (episodes → channels, channels → close); S
        # toggles seen on the highlighted episode.
        if action in (Action.CHANNEL_UP, Action.CHANNEL_DOWN):
            delta = -1 if action is Action.CHANNEL_UP else 1
            self._browser_move(delta)
        elif action in (Action.SEEK_FWD, Action.NEXT, Action.PLAY_PAUSE):
            self._browser_forward()
        elif action in (Action.SEEK_BACK, Action.PREV, Action.RESTART):
            self._browser_back()
        elif action is Action.MARK_SEEN:
            self._browser_toggle_seen()
        # TOGGLE_TRAILER / SLEEP / unmapped: ignored inside the browser.

    def _browser_move(self, delta: int) -> None:
        if self._browser_mode == "channels":
            n = len(self.channels)
            self._br_ch_cursor = (self._br_ch_cursor + delta) % n
            self._br_ch_top = scroll_to(
                self._br_ch_cursor, self._br_ch_top, n, BROWSER_ROWS
            )
        else:
            ch = self.channels[self._br_ch_cursor]
            n = len(ch.videos)
            self._br_ep_cursor = (self._br_ep_cursor + delta) % n
            self._br_ep_top = scroll_to(
                self._br_ep_cursor, self._br_ep_top, n, BROWSER_ROWS
            )
        self._render_browser()

    def _browser_forward(self) -> None:
        if self._browser_mode == "channels":
            # Drill into the highlighted channel's episodes, parked on its
            # saved/current video (so re-entering the channel you're watching
            # lands on the episode you're on).
            self._browser_mode = "episodes"
            ch = self.channels[self._br_ch_cursor]
            self._br_ep_cursor = self._resume_index_for_channel(self._br_ch_cursor)
            self._br_ep_top = scroll_to(
                self._br_ep_cursor, 0, len(ch.videos), BROWSER_ROWS
            )
            self._render_browser()
        else:
            self._browser_play()

    def _browser_back(self) -> None:
        if self._browser_mode == "episodes":
            self._browser_mode = "channels"
            self._render_browser()
        else:
            self._close_browser(restore=True)

    def _browser_play(self) -> None:
        """Play the highlighted episode and drop out of the browser.

        Selecting the exact video that's already playing does **not** reload it
        (that would seek back to the stale resume point); we just resume viewing
        from the current position.
        """
        same = (
            self._br_ch_cursor == self.ch_idx
            and self._br_ep_cursor == self.vid_idx
        )
        self.ch_idx = self._br_ch_cursor
        self.vid_idx = self._br_ep_cursor
        self._browser_mode = None
        if same:
            self._restore_after_browser()
        else:
            self._play_current(resume=True)  # loads, plays, clears overlay, titles

    def _browser_toggle_seen(self) -> None:
        if self._browser_mode != "episodes" or self.state is None:
            return
        ch = self.channels[self._br_ch_cursor]
        rel = ch.videos[self._br_ep_cursor]
        if self.state.is_seen(rel):
            self.state.update_video(rel, seen=False)
        else:
            self.state.mark_seen(rel)
        self._request_save()
        self._render_browser()

    # -- periodic checkpoint ---------------------------------------------

    def _checkpoint_loop(self) -> None:
        while self._running:
            time.sleep(self.cfg.checkpoint_seconds)
            with self._lock:
                if not bool(self._prop("pause", False)):
                    self._save_progress()
