"""Manager threading tests with a fake mpv (stdlib unittest, no real mpv/Pi).

These exercise the two deadlock paths the threading model is built to avoid:

* a video reaching EOF must auto-advance (and must not block), and
* EOF events racing with input actions must never deadlock.

They also encode the core invariant directly: the manager makes **no blocking
IPC call** on these paths — only fire-and-forget commands.

Run from the repo root:  python3 -m unittest discover -s tests -v
"""

import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The manager imports input_kbd → evdev, which is Linux-only and absent on a
# typical dev laptop. Stub a minimal evdev so the module is importable; these
# tests never touch real input.
try:  # pragma: no cover - on a Pi the real module is present
    import evdev  # noqa: F401
except Exception:  # pragma: no cover - exercised on non-Linux dev machines
    _evdev = types.ModuleType("evdev")
    _ecodes = types.ModuleType("evdev.ecodes")
    _ids: dict[str, int] = {}

    def _ecodes_getattr(name: str) -> int:
        if name.startswith("KEY_"):
            return _ids.setdefault(name, len(_ids) + 100)
        raise AttributeError(name)

    _ecodes.__getattr__ = _ecodes_getattr  # type: ignore[attr-defined]
    _ecodes.EV_KEY = 1
    _ecodes.KEY = {}
    _evdev.ecodes = _ecodes
    _evdev.InputDevice = object  # type: ignore[attr-defined]
    _evdev.list_devices = lambda: []  # type: ignore[attr-defined]
    sys.modules["evdev"] = _evdev
    sys.modules["evdev.ecodes"] = _ecodes

from pondtv.actions import Action  # noqa: E402
from pondtv.config import Config  # noqa: E402
from pondtv.manager import Manager  # noqa: E402


class FakeMpv:
    """Records commands and lets a test emit mpv events.

    The point of the fake is to make blocking vs. fire-and-forget visible: every
    blocking call (``command``/``get_property``/``set_property``) is recorded in
    :attr:`blocking_calls`, which the tests assert stays empty on the hot paths.
    """

    def __init__(self) -> None:
        self.async_calls: list[tuple] = []
        self.blocking_calls: list[tuple] = []
        self.loaded: list[str] = []
        self._handlers: list = []
        self._lock = threading.Lock()

    # connection / observers
    def connect(self) -> None:
        pass

    def is_connected(self) -> bool:
        return True

    def observe_property(self, name, obs_id=1) -> None:
        pass

    def on_event(self, handler) -> None:
        self._handlers.append(handler)

    # blocking API (should NOT be used on the hot paths)
    def command(self, *args, timeout=5.0):
        with self._lock:
            self.blocking_calls.append(args)
        return None

    def get_property(self, name):
        with self._lock:
            self.blocking_calls.append(("get_property", name))
        return None

    def set_property(self, name, value):
        with self._lock:
            self.blocking_calls.append(("set_property", name, value))

    # fire-and-forget API
    def command_async(self, *args) -> None:
        with self._lock:
            self.async_calls.append(args)
            if args and args[0] == "loadfile":
                self.loaded.append(args[1])

    def set_property_async(self, name, value) -> None:
        with self._lock:
            self.async_calls.append(("set_property", name, value))

    # test helper
    def emit(self, event: dict) -> None:
        for handler in list(self._handlers):
            handler(event)


def _make_manager(tmp: Path) -> tuple[Manager, FakeMpv]:
    """A manager wired to a fake mpv and a two-video channel, mounted."""
    cat = tmp / "Clips"
    cat.mkdir(parents=True)
    (cat / "01.mp4").write_bytes(b"")
    (cat / "02.mp4").write_bytes(b"")

    mgr = Manager(Config(resume_min_seconds=60.0))
    fake = FakeMpv()
    mgr.mpv = fake
    fake.on_event(mgr._on_mpv_event)  # what _connect_mpv() does at start()
    mgr._running = True
    mgr._on_mount(str(tmp))  # builds channels + plays the first video
    return mgr, fake


class ManagerEofTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_mount_plays_first_video(self) -> None:
        mgr, fake = _make_manager(self.tmp)
        self.assertEqual(len(mgr.channels), 1)
        self.assertEqual(mgr.vid_idx, 0)
        self.assertTrue(fake.loaded[-1].endswith("01.mp4"))
        self.assertEqual(fake.blocking_calls, [])  # invariant: no blocking IPC

    def test_eof_advances_to_next_video(self) -> None:
        mgr, fake = _make_manager(self.tmp)
        loaded_before = len(fake.loaded)

        # The regression: this used to deadlock (blocking loadfile on the reader
        # thread). It must return promptly and advance to 02.mp4.
        fake.emit({"event": "property-change", "name": "eof-reached", "data": True})

        self.assertEqual(mgr.vid_idx, 1)
        self.assertGreater(len(fake.loaded), loaded_before)
        self.assertTrue(fake.loaded[-1].endswith("02.mp4"))
        self.assertEqual(fake.blocking_calls, [])  # still no blocking IPC

    def test_eof_marks_seen(self) -> None:
        mgr, fake = _make_manager(self.tmp)
        first_rel = mgr.channels[0].videos[0]
        fake.emit({"event": "property-change", "name": "eof-reached", "data": True})
        self.assertTrue(mgr.state.is_seen(first_rel))

    def test_eof_wraps_at_end_of_channel(self) -> None:
        mgr, fake = _make_manager(self.tmp)
        fake.emit({"event": "property-change", "name": "eof-reached", "data": True})  # →1
        fake.emit({"event": "property-change", "name": "eof-reached", "data": True})  # →0
        self.assertEqual(mgr.vid_idx, 0)

    def test_pending_seek_applied_on_playback_restart(self) -> None:
        mgr, fake = _make_manager(self.tmp)
        # Pretend the first video has a resume point, then re-load it.
        rel = mgr.channels[0].videos[0]
        mgr.state.update_video(rel, position=300.0, duration=1200.0)
        with mgr._lock:
            mgr._play_current(resume=True)
        fake.async_calls.clear()
        fake.emit({"event": "playback-restart"})
        self.assertIn(("seek", 300.0, "absolute"), fake.async_calls)
        self.assertEqual(fake.blocking_calls, [])


class ManagerConcurrencyTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_eof_and_actions_do_not_deadlock(self) -> None:
        mgr, fake = _make_manager(self.tmp)
        stop = threading.Event()

        def hammer_actions() -> None:
            while not stop.is_set():
                mgr._on_action(Action.SEEK_FWD)
                mgr._on_action(Action.PLAY_PAUSE)
                mgr._on_action(Action.CHANNEL_UP)

        def hammer_eof() -> None:
            while not stop.is_set():
                fake.emit({"event": "property-change", "name": "eof-reached", "data": True})

        threads = [
            threading.Thread(target=hammer_actions),
            threading.Thread(target=hammer_actions),
            threading.Thread(target=hammer_eof),
        ]
        for t in threads:
            t.start()
        time.sleep(0.4)
        stop.set()
        for t in threads:
            t.join(timeout=3.0)

        for t in threads:
            self.assertFalse(t.is_alive(), "deadlock: a worker thread never returned")
        self.assertEqual(fake.blocking_calls, [], "blocking IPC used on a hot path")


if __name__ == "__main__":
    unittest.main()
