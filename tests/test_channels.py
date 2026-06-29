"""Unit tests for channel derivation + natural sort (stdlib unittest, no pip).

Run from the repo root:  python3 -m unittest discover -s tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

# Make the repo root importable when run via `python3 -m unittest` from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pondtv.channels import Channel, build_channels, natural_key  # noqa: E402


def _touch(root: Path, *rel_parts: str) -> None:
    p = root.joinpath(*rel_parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"")


class NaturalKeyTests(unittest.TestCase):
    def test_numbers_sort_numerically_not_lexically(self):
        names = ["E10", "E2", "E1", "E20", "E3"]
        self.assertEqual(
            sorted(names, key=natural_key), ["E1", "E2", "E3", "E10", "E20"]
        )

    def test_seasons_order_before_episodes_across_folders(self):
        paths = [
            "Show/Season 02/Show - S02E01.mp4",
            "Show/Season 01/Show - S01E10.mp4",
            "Show/Season 01/Show - S01E02.mp4",
        ]
        self.assertEqual(
            sorted(paths, key=natural_key),
            [
                "Show/Season 01/Show - S01E02.mp4",
                "Show/Season 01/Show - S01E10.mp4",
                "Show/Season 02/Show - S02E01.mp4",
            ],
        )

    def test_case_insensitive(self):
        self.assertEqual(sorted(["banana", "Apple"], key=natural_key), ["Apple", "banana"])


class BuildChannelsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        # A tree mirroring the README layout.
        _touch(self.root, "Movies", "The Film", "The Film.mkv")
        _touch(self.root, "Movies", "The Film", "The Film.srt")  # subtitle, not a video
        _touch(self.root, "TV_Shows", "ShowName", "Season 01", "ShowName - S01E01.mp4")
        _touch(self.root, "TV_Shows", "ShowName", "Season 01", "ShowName - S01E02.mp4")
        _touch(self.root, "TV_Shows", "ShowName", "Season 02", "ShowName - S02E01.mp4")
        _touch(self.root, "TV_Shows", "ShowName", "Specials", "ShowName - Special.mp4")
        _touch(self.root, "Ripped YT Channels", "Video 01.mp4")
        _touch(self.root, "Ripped YT Channels", "Video 02.mp4")
        _touch(self.root, "Selections", "Clip A.mp4")
        _touch(self.root, "Selections", "Clip B.mp4")
        # State dir + junk that must be ignored.
        _touch(self.root, ".pondtv", "state.json")
        _touch(self.root, ".pondtv", "should-not-appear.mp4")
        _touch(self.root, "TV_Shows", "ShowName", ".Trash", "junk.mp4")
        _touch(self.root, "Movies", "The Film", "notes.txt")

    def tearDown(self):
        self._tmp.cleanup()

    def _by_path(self, channels):
        return {c.path: c for c in channels}

    def test_channel_set_and_order(self):
        channels = build_channels(self.root)
        # Natural-sorted by channel path.
        self.assertEqual(
            [c.path for c in channels],
            [
                "Movies/The Film",
                "Ripped YT Channels",
                "Selections",
                "TV_Shows/ShowName",
            ],
        )

    def test_show_collapses_seasons_and_specials_in_order(self):
        ch = self._by_path(build_channels(self.root))["TV_Shows/ShowName"]
        self.assertEqual(
            ch.videos,
            [
                "TV_Shows/ShowName/Season 01/ShowName - S01E01.mp4",
                "TV_Shows/ShowName/Season 01/ShowName - S01E02.mp4",
                "TV_Shows/ShowName/Season 02/ShowName - S02E01.mp4",
                "TV_Shows/ShowName/Specials/ShowName - Special.mp4",
            ],
        )

    def test_loose_files_form_one_category_channel(self):
        ch = self._by_path(build_channels(self.root))["Ripped YT Channels"]
        self.assertEqual(ch.name, "Ripped YT Channels")
        self.assertEqual(
            ch.videos, ["Ripped YT Channels/Video 01.mp4", "Ripped YT Channels/Video 02.mp4"]
        )

    def test_movie_folder_is_one_channel(self):
        ch = self._by_path(build_channels(self.root))["Movies/The Film"]
        self.assertEqual(ch.videos, ["Movies/The Film/The Film.mkv"])  # .srt excluded

    def test_hidden_dirs_excluded(self):
        channels = build_channels(self.root)
        all_videos = [v for c in channels for v in c.videos]
        self.assertNotIn(".pondtv/should-not-appear.mp4", all_videos)
        self.assertFalse(any(".Trash" in v for v in all_videos))

    def test_category_with_both_loose_and_subfolders(self):
        # Movies gets a loose trailer AND keeps its The Film/ subfolder channel.
        _touch(self.root, "Movies", "Trailer.mp4")
        channels = self._by_path(build_channels(self.root))
        self.assertIn("Movies", channels)  # the loose-files channel for the category
        self.assertEqual(channels["Movies"].videos, ["Movies/Trailer.mp4"])
        self.assertIn("Movies/The Film", channels)  # subfolder channel still present


if __name__ == "__main__":
    unittest.main(verbosity=2)
