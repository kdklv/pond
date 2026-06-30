"""Browser overlay tests — open/close, drill-down navigation, and the threading
invariant that matters: no blocking IPC on any browse path (same rule as the
playback tests in test_manager.py).

Pure rendering (``render_browser`` / ``scroll_to``) is checked without a manager;
the interaction tests use a fake mpv that records every call so we can assert
exactly which commands fire and that none of them block.

Run from the repo root:  python3 -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Importing test_manager runs its evdev stub (Linux-only) so pondtv.manager
# is importable on a non-Pi dev machine. We reuse its FakeMpv verbatim.
from test_manager import FakeMpv  # noqa: E402

from pondtv.actions import Action  # noqa: E402
from pondtv.browser import BROWSER_ROWS, render_browser, scroll_to  # noqa: E402
from pondtv.channels import build_channels  # noqa: E402
from pondtv.config import Config  # noqa: E402
from pondtv.manager import Manager  # noqa: E402
from pondtv.state import State  # noqa: E402


# --- pure rendering / scroll --------------------------------------------------


class ScrollTests(unittest.TestCase):
    def test_fits_in_viewport_no_scroll(self):
        self.assertEqual(scroll_to(3, 0, 5, 12), 0)

    def test_cursor_below_viewport_advances_top(self):
        # 20 items, 12 rows; cursor jumps to index 15 → top must follow.
        self.assertEqual(scroll_to(15, 0, 20, 12), 4)

    def test_cursor_above_viewport_resets_top(self):
        # scrolled to the bottom, cursor jumps back up to index 2.
        self.assertEqual(scroll_to(2, 8, 20, 12), 2)

    def test_last_page_kept_full(self):
        # cursor at 19 (last), top was 8 → 19-11=8 keeps it on the bottom row;
        # min(8, 20-12)=8, so top stays 8 (no float up).
        self.assertEqual(scroll_to(19, 8, 20, 12), 8)
        # but a too-far top clamps down so the last page is full
        self.assertEqual(scroll_to(10, 15, 20, 12), 8)


class RenderBrowserTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "Clips").mkdir()
        for n in ("01.mp4", "02.mp4", "03.mp4"):
            (self.root / "Clips" / n).write_bytes(b"")
        show = self.root / "TV_Shows" / "Show A"
        (show / "Season 01").mkdir(parents=True)
        (show / "Season 02").mkdir(parents=True)
        for n in ("S01E01.mkv", "S01E02.mkv"):
            (show / "Season 01" / n).write_bytes(b"")
        for n in ("S02E01.mkv", "S02E02.mkv"):
            (show / "Season 02" / n).write_bytes(b"")
        showb = self.root / "TV_Shows" / "Show B"
        (showb / "Season 01").mkdir(parents=True)
        for n in ("S01E01.mkv", "S01E02.mkv"):
            (showb / "Season 01" / n).write_bytes(b"")
        self.channels = build_channels(self.root)
        self.state = State(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_channels_view_lists_all_with_counts(self):
        ass = render_browser("channels", self.channels, 0, 0, 0, 0, self.state)
        self.assertIn("BROWSE", ass)
        self.assertIn("3 CHANNELS", ass)
        for ch in self.channels:
            self.assertIn(ch.name, ass)

    def test_episodes_view_titles_channel_and_lists_videos(self):
        ass = render_browser("episodes", self.channels, 1, 0, 0, 0, self.state)
        self.assertIn("SHOW A", ass)
        self.assertIn("4 EPISODES", ass)
        # episode labels are basenames without extension
        self.assertIn("S01E01", ass)
        self.assertIn("S02E02", ass)

    def test_seen_episode_marked_with_dot(self):
        rel = self.channels[1].videos[0]  # Show A S01E01
        self.state.mark_seen(rel)
        ass = render_browser("episodes", self.channels, 1, 0, 0, 0, self.state)
        # the seen row carries a middle dot; the unwatched rows don't
        self.assertIn("· S01E01", ass)
        self.assertIn("  S01E02", ass)

    def test_cursor_row_is_bright(self):
        ass = render_browser("channels", self.channels, 1, 0, 0, 0, self.state)
        # the cursor marker ▸ prefixes the highlighted channel
        self.assertIn("▸ Show A", ass)
        self.assertIn("  Clips", ass)


# --- interaction (with a fake mpv) -------------------------------------------


def _overlay_count(fake: FakeMpv) -> int:
    return sum(1 for c in fake.async_calls if c and c[0] == "osd-overlay")


def _pause_sets(fake: FakeMpv) -> list:
    return [v for name, v in (
        (c[1], c[2]) for c in fake.async_calls if c and c[0] == "set_property" and c[1] == "pause"
    )]


def _make_manager(tmp: Path) -> tuple[Manager, FakeMpv]:
    """A manager with three channels (Clips: 3, Show A: 4, Show B: 2)."""
    (tmp / "Clips").mkdir()
    for n in ("01.mp4", "02.mp4", "03.mp4"):
        (tmp / "Clips" / n).write_bytes(b"")
    show = tmp / "TV_Shows" / "Show A"
    (show / "Season 01").mkdir(parents=True)
    (show / "Season 02").mkdir(parents=True)
    for n in ("S01E01.mkv", "S01E02.mkv"):
        (show / "Season 01" / n).write_bytes(b"")
    for n in ("S02E01.mkv", "S02E02.mkv"):
        (show / "Season 02" / n).write_bytes(b"")
    showb = tmp / "TV_Shows" / "Show B"
    (showb / "Season 01").mkdir(parents=True)
    for n in ("S01E01.mkv", "S01E02.mkv"):
        (showb / "Season 01" / n).write_bytes(b"")

    mgr = Manager(Config(resume_min_seconds=60.0))
    fake = FakeMpv()
    mgr.mpv = fake
    fake.on_event(mgr._on_mpv_event)
    mgr._running = True
    mgr._on_mount(str(tmp))  # builds channels, plays Clips/01.mp4
    fake.async_calls.clear()
    return mgr, fake


class BrowserInteractionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.mgr, self.fake = _make_manager(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def test_three_channels_built(self):
        self.assertEqual([c.name for c in self.mgr.channels], ["Clips", "Show A", "Show B"])

    def test_browse_opens_at_current_channel_and_pauses(self):
        self.mgr._on_action(Action.CHANNEL_UP)  # now on Show A (ch_idx=1)
        self.fake.async_calls.clear()

        self.mgr._on_action(Action.BROWSE)

        self.assertEqual(self.mgr._browser_mode, "channels")
        self.assertEqual(self.mgr._br_ch_cursor, 1)  # parked on the current channel
        self.assertGreater(_overlay_count(self.fake), 0)  # overlay drawn
        # playback paused on open, position checkpointed (no blocking IPC)
        self.assertIn(True, _pause_sets(self.fake))
        self.assertEqual(self.fake.blocking_calls, [])

    def test_browse_with_no_drive_is_noop(self):
        self.mgr._on_unmount()
        self.fake.async_calls.clear()
        before = len(self.fake.async_calls)
        self.mgr._on_action(Action.BROWSE)
        self.assertIsNone(self.mgr._browser_mode)
        self.assertEqual(len(self.fake.async_calls), before)

    def test_browse_toggles_closed(self):
        self.mgr._on_action(Action.BROWSE)
        self.assertIsNotNone(self.mgr._browser_mode)
        self.mgr._on_action(Action.BROWSE)
        self.assertIsNone(self.mgr._browser_mode)

    def test_channel_cursor_moves_and_wraps(self):
        self.mgr._on_action(Action.BROWSE)
        self.mgr._on_action(Action.CHANNEL_DOWN)
        self.assertEqual(self.mgr._br_ch_cursor, 1)
        self.mgr._on_action(Action.CHANNEL_DOWN)
        self.assertEqual(self.mgr._br_ch_cursor, 2)
        self.mgr._on_action(Action.CHANNEL_DOWN)  # wrap → 0
        self.assertEqual(self.mgr._br_ch_cursor, 0)
        self.mgr._on_action(Action.CHANNEL_UP)  # wrap back → 2
        self.assertEqual(self.mgr._br_ch_cursor, 2)
        self.assertEqual(self.fake.blocking_calls, [])

    def test_drill_into_episodes_lands_on_current_video(self):
        # Put ourselves on Show A, episode index 2 (S02E01).
        self.mgr._on_action(Action.CHANNEL_UP)
        self.mgr._on_action(Action.NEXT)
        self.mgr._on_action(Action.NEXT)
        self.assertEqual(self.mgr.vid_idx, 2)
        self.fake.async_calls.clear()

        self.mgr._on_action(Action.BROWSE)
        self.mgr._on_action(Action.SEEK_FWD)  # drill in

        self.assertEqual(self.mgr._browser_mode, "episodes")
        self.assertEqual(self.mgr._br_ep_cursor, 2)  # channel's current video

    def test_episode_cursor_moves(self):
        self.mgr._on_action(Action.CHANNEL_UP)  # Show A
        self.mgr._on_action(Action.BROWSE)
        self.mgr._on_action(Action.SEEK_FWD)  # episodes pane
        self.mgr._on_action(Action.CHANNEL_DOWN)
        self.assertEqual(self.mgr._br_ep_cursor, 1)
        self.assertEqual(self.mgr._browser_mode, "episodes")

    def test_play_selected_loads_and_closes(self):
        self.mgr._on_action(Action.CHANNEL_UP)  # Show A, ep 0
        self.mgr._on_action(Action.BROWSE)
        self.mgr._on_action(Action.SEEK_FWD)  # episodes
        self.mgr._on_action(Action.CHANNEL_DOWN)  # cursor → ep 1
        self.fake.loaded.clear()

        self.mgr._on_action(Action.PLAY_PAUSE)  # play highlighted

        self.assertIsNone(self.mgr._browser_mode)
        self.assertEqual(self.mgr.ch_idx, 1)
        self.assertEqual(self.mgr.vid_idx, 1)
        self.assertTrue(self.fake.loaded[-1].endswith("S01E02.mkv"))
        self.assertEqual(self.fake.blocking_calls, [])

    def test_play_same_video_does_not_reload(self):
        # Currently playing Clips/01.mp4 (ch 0, ep 0).
        self.mgr._on_action(Action.BROWSE)         # channels, cursor 0
        self.mgr._on_action(Action.SEEK_FWD)       # episodes, cursor 0 (current)
        self.fake.loaded.clear()
        self.fake.async_calls.clear()

        self.mgr._on_action(Action.PLAY_PAUSE)     # "play" the same video

        self.assertIsNone(self.mgr._browser_mode)
        self.assertEqual(self.fake.loaded, [])     # no reload
        # playback restored to whatever it was before opening (here: playing)
        self.assertIn(False, _pause_sets(self.fake))

    def test_back_from_episodes_returns_to_channels(self):
        self.mgr._on_action(Action.CHANNEL_UP)
        self.mgr._on_action(Action.BROWSE)
        self.mgr._on_action(Action.SEEK_FWD)  # episodes
        self.fake.loaded.clear()

        self.mgr._on_action(Action.SEEK_BACK)  # ← back

        self.assertEqual(self.mgr._browser_mode, "channels")
        self.assertEqual(self.fake.loaded, [])

    def test_back_from_channels_closes_browser(self):
        self.mgr._on_action(Action.BROWSE)
        self.fake.loaded.clear()

        self.mgr._on_action(Action.RESTART)  # Backspace = back at channel list

        self.assertIsNone(self.mgr._browser_mode)
        self.assertEqual(self.fake.loaded, [])

    def test_mark_seen_toggles_in_episodes(self):
        self.mgr._on_action(Action.CHANNEL_UP)  # Show A
        self.mgr._on_action(Action.BROWSE)
        self.mgr._on_action(Action.SEEK_FWD)      # episodes, cursor on S01E01
        rel = self.mgr.channels[1].videos[0]
        self.assertFalse(self.mgr.state.is_seen(rel))

        self.mgr._on_action(Action.MARK_SEEN)
        self.assertTrue(self.mgr.state.is_seen(rel))

        self.mgr._on_action(Action.MARK_SEEN)     # toggle off
        self.assertFalse(self.mgr.state.is_seen(rel))

    def test_mark_seen_in_channels_does_nothing(self):
        self.mgr._on_action(Action.BROWSE)  # channels pane
        before = self.mgr.state.data
        self.mgr._on_action(Action.MARK_SEEN)
        self.assertEqual(self.mgr.state.data, before)

    def test_eof_ignored_while_browser_open(self):
        self.mgr._on_action(Action.BROWSE)
        vid_before = self.mgr.vid_idx
        self.fake.loaded.clear()

        self.fake.emit({"event": "property-change", "name": "eof-reached", "data": True})

        self.assertEqual(self.mgr.vid_idx, vid_before)  # no auto-advance
        self.assertEqual(self.fake.loaded, [])
        self.assertEqual(self.mgr._browser_mode, "channels")  # browse overlay intact

    def test_unmount_closes_browser(self):
        self.mgr._on_action(Action.BROWSE)
        self.assertIsNotNone(self.mgr._browser_mode)
        self.mgr._on_unmount()
        self.assertIsNone(self.mgr._browser_mode)

    def test_open_while_paused_restores_paused(self):
        self.mgr._on_action(Action.PLAY_PAUSE)  # pause (was playing)
        self.fake.async_calls.clear()
        self.mgr._on_action(Action.BROWSE)
        self.assertTrue(self.mgr._browser_was_paused)
        self.mgr._on_action(Action.BROWSE)  # close
        # closing a paused-opened browser leaves it paused (pause UI shown)
        self.assertIn(True, _pause_sets(self.fake))

    def test_scroll_follows_cursor_with_many_channels(self):
        # A drive with exactly 20 channels so scrolling kicks in. Built inline
        # (not via _make_manager, which adds its own Clips/Show A/Show B).
        with tempfile.TemporaryDirectory() as many:
            root = Path(many) / "Many"
            root.mkdir()
            for i in range(20):
                ch = root / f"ch{i:02d}"
                ch.mkdir()
                (ch / "v.mkv").write_bytes(b"")
            mgr = Manager(Config(resume_min_seconds=60.0))
            fake = FakeMpv()
            mgr.mpv = fake
            fake.on_event(mgr._on_mpv_event)
            mgr._running = True
            mgr._on_mount(many)
            fake.async_calls.clear()
        self.assertEqual(len(mgr.channels), 20)
        mgr._on_action(Action.BROWSE)
        for _ in range(15):
            mgr._on_action(Action.CHANNEL_DOWN)  # list convention: ↓ = +1
        # cursor at 15, viewport top keeps it within the last page
        self.assertEqual(mgr._br_ch_cursor, 15)
        self.assertLessEqual(mgr._br_ch_top, 15)
        self.assertGreaterEqual(mgr._br_ch_top + BROWSER_ROWS - 1, 15)
        self.assertEqual(fake.blocking_calls, [])

    def test_no_blocking_ipc_across_browse_session(self):
        # A full browse session: open, surf, drill, surf, play.
        self.mgr._on_action(Action.BROWSE)
        self.mgr._on_action(Action.CHANNEL_DOWN)
        self.mgr._on_action(Action.SEEK_FWD)
        self.mgr._on_action(Action.CHANNEL_DOWN)
        self.mgr._on_action(Action.CHANNEL_DOWN)
        self.mgr._on_action(Action.MARK_SEEN)
        self.mgr._on_action(Action.PLAY_PAUSE)
        self.assertEqual(self.fake.blocking_calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
