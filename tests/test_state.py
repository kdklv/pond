"""Unit tests for USB watch-state: persistence, atomicity, smart-seen."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pondtv.state import State, is_smart_seen  # noqa: E402


class SmartSeenTests(unittest.TestCase):
    def test_within_tail_minutes(self):
        # 2400s runtime, stopped with 8 min left → seen (tail_minutes=10).
        self.assertTrue(is_smart_seen(2400 - 8 * 60, 2400))

    def test_within_tail_percent_but_not_minutes(self):
        # 100s clip, at 85% → within last 20%, even though minutes-tail is huge.
        self.assertTrue(is_smart_seen(85, 100, tail_minutes=10, tail_percent=20))

    def test_middle_is_not_seen(self):
        self.assertFalse(is_smart_seen(1200, 2400))

    def test_zero_duration_is_not_seen(self):
        self.assertFalse(is_smart_seen(0, 0))


class StatePersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_update_and_retrieve(self):
        st = State(self.root)
        st.update_video("Movies/Film/Film.mkv", position=123.5, duration=2400.0)
        rec = st.get_video("Movies/Film/Film.mkv")
        self.assertEqual(rec["position"], 123.5)
        self.assertEqual(rec["duration"], 2400.0)
        self.assertFalse(rec["seen"])
        self.assertIsNotNone(rec["last_watched"])

    def test_unseen_video_defaults(self):
        st = State(self.root)
        rec = st.get_video("nope.mkv")
        self.assertEqual(rec["position"], 0.0)
        self.assertFalse(rec["seen"])

    def test_save_reload_roundtrip(self):
        st = State(self.root)
        st.update_video("a/b.mkv", position=42.0, duration=100.0)
        st.set_channel_current("TV_Shows/Show", "TV_Shows/Show/S01E01.mkv")
        st.save()

        reloaded = State(self.root)
        self.assertEqual(reloaded.resume_position("a/b.mkv"), 42.0)
        self.assertEqual(
            reloaded.get_channel_current("TV_Shows/Show"),
            "TV_Shows/Show/S01E01.mkv",
        )

    def test_save_is_atomic_no_tmp_left(self):
        st = State(self.root)
        st.update_video("x.mkv", position=1.0)
        st.save()
        self.assertTrue(st.path.exists())
        self.assertFalse((st.state_dir / "state.json.tmp").exists())
        # File is valid JSON with the expected top-level shape.
        data = json.loads(st.path.read_text())
        self.assertIn("videos", data)
        self.assertIn("channels", data)

    def test_corrupt_file_loads_empty(self):
        st = State(self.root)
        st.save()
        st.path.write_text("{ this is not valid json ::::")
        recovered = State(self.root)  # must not raise
        self.assertEqual(recovered.data, {"videos": {}, "channels": {}})

    def test_missing_file_loads_empty(self):
        st = State(self.root)  # nothing on disk yet
        self.assertEqual(st.data, {"videos": {}, "channels": {}})

    def test_mark_seen_resets_position(self):
        st = State(self.root)
        st.update_video("e.mkv", position=900.0, duration=1000.0)
        st.mark_seen("e.mkv")
        rec = st.get_video("e.mkv")
        self.assertTrue(rec["seen"])
        self.assertEqual(rec["position"], 0.0)

    def test_keys_are_relative_posix(self):
        # The stored key is exactly the relative path we pass (never absolute).
        st = State(self.root)
        st.update_video("TV_Shows/Show/Season 01/Show - S01E02.mkv", position=5.0)
        st.save()
        data = json.loads(st.path.read_text())
        self.assertIn("TV_Shows/Show/Season 01/Show - S01E02.mkv", data["videos"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
