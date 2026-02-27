#!/usr/bin/env python3
"""
Quick integration test for the three pure-logic PondTV components:
  MediaScanner → DatabaseManager → PlaylistEngine

No hardware required (no USB drive, no mpv, no D-Bus).
"""

import os
import sys
import shutil
import tempfile

# Make sure we can import the package from here
sys.path.insert(0, os.path.dirname(__file__))

# Patch the minimum file size to 0 so we don't need 50 MB dummy files.
import pondtv.media_scanner as _ms_mod
_ms_mod.MediaScanner.MIN_FILE_SIZE_MB = 0

from pondtv.media_scanner import MediaScanner
from pondtv.database_manager import DatabaseManager
from pondtv.playlist_engine import PlaylistEngine


def make_file(path: str):
    """Create a tiny placeholder video file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b'\x00' * 1024)  # 1 KB — well below normal 50 MB threshold


def build_media_tree(root: str):
    """
    Creates this structure under *root*:

        Movies/
          The Matrix (1999)/
            The.Matrix.1999.1080p.BluRay.mkv   ← main film
            The.Matrix.1999.sample.mkv          ← should be ignored (sample)
        TV_Shows/
          Cosmic Wanderers/
            Season 01/
              Cosmic.Wanderers.S01E01.mp4
              Cosmic.Wanderers.S01E02.mp4
            Season 02/
              Cosmic.Wanderers.S02E01.mp4
          Mini Doc/                             ← single-video documentary
            Mini.Doc.2023.mp4
    """
    # Movies
    make_file(os.path.join(root, "Movies", "The Matrix (1999)", "The.Matrix.1999.1080p.BluRay.mkv"))
    make_file(os.path.join(root, "Movies", "The Matrix (1999)", "The.Matrix.1999.sample.mkv"))

    # TV show with two seasons
    make_file(os.path.join(root, "TV_Shows", "Cosmic Wanderers", "Season 01", "Cosmic.Wanderers.S01E01.mp4"))
    make_file(os.path.join(root, "TV_Shows", "Cosmic Wanderers", "Season 01", "Cosmic.Wanderers.S01E02.mp4"))
    make_file(os.path.join(root, "TV_Shows", "Cosmic Wanderers", "Season 02", "Cosmic.Wanderers.S02E01.mp4"))

    # Single-video documentary (no season/episode markers)
    make_file(os.path.join(root, "TV_Shows", "Mini Doc", "Mini.Doc.2023.mp4"))


# ─────────────────────────────────────────────────────────────────────────────
# Run the test
# ─────────────────────────────────────────────────────────────────────────────

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
failures = []


def check(label: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  [{PASS}] {label}")
    else:
        msg = f"{label}" + (f" — {detail}" if detail else "")
        print(f"  [{FAIL}] {msg}")
        failures.append(msg)


tmpdir = tempfile.mkdtemp(prefix="pondtv_test_")
try:
    print(f"\nTest media tree: {tmpdir}\n")
    build_media_tree(tmpdir)

    # ── 1. MediaScanner ───────────────────────────────────────────────────────
    print("── MediaScanner ──────────────────────────────────────────────────────")
    scanner = MediaScanner(tmpdir)
    db = scanner.scan()

    movies = db.get('movies', {})
    tv    = db.get('tv_shows', {})

    check("movies is a dict",          isinstance(movies, dict))
    check("The Matrix found",          'The Matrix' in movies,
          f"found: {list(movies.keys())}")
    check("sample file excluded",      all('sample' not in v.get('filepath','')
                                           for v in movies.values()))
    check("movie status is Unseen",    movies.get('The Matrix', {}).get('status') == 'Unseen')

    cw = tv.get('Cosmic Wanderers', {})
    check("Cosmic Wanderers found",    bool(cw), f"found shows: {list(tv.keys())}")
    check("Season 01 present",         'Season 01' in cw.get('seasons', {}))
    check("Season 02 present",         'Season 02' in cw.get('seasons', {}))
    s1_eps = cw.get('seasons', {}).get('Season 01', {}).get('episodes', [])
    check("Season 01 has 2 episodes",  len(s1_eps) == 2, f"got {len(s1_eps)}")
    s2_eps = cw.get('seasons', {}).get('Season 02', {}).get('episodes', [])
    check("Season 02 has 1 episode",   len(s2_eps) == 1, f"got {len(s2_eps)}")
    check("Mini Doc found",            'Mini Doc' in tv,
          f"found shows: {list(tv.keys())}")

    # ── 2. DatabaseManager ────────────────────────────────────────────────────
    print("\n── DatabaseManager ───────────────────────────────────────────────────")
    db_path = os.path.join(tmpdir, "media_library.yml")
    mgr = DatabaseManager(db_path)

    saved = mgr.save(db)
    check("save() returns True",       saved is True)
    check("YAML file created",         os.path.isfile(db_path))

    loaded = mgr.load()
    check("load() returns dict",       isinstance(loaded, dict))
    check("movies round-trips",        'The Matrix' in loaded.get('movies', {}))
    check("tv_shows round-trips",      'Cosmic Wanderers' in loaded.get('tv_shows', {}))

    valid = mgr._is_valid(loaded)
    check("validation passes",         valid)

    invalid = mgr._is_valid({'movies': [], 'tv_shows': {}})
    check("validation rejects bad data", not invalid)

    # load_and_validate should return existing data (no rescan needed)
    validated = mgr.load_and_validate(tmpdir)
    check("load_and_validate returns data", bool(validated))

    # ── 3. PlaylistEngine ─────────────────────────────────────────────────────
    print("\n── PlaylistEngine ────────────────────────────────────────────────────")
    engine  = PlaylistEngine(loaded)
    playlist = engine.create_playlist()

    check("playlist is non-empty",     len(playlist) > 0, f"got {len(playlist)}")

    # Mark The Matrix as Seen and check it disappears from the next playlist
    loaded['movies']['The Matrix']['status'] = 'Seen'
    engine2  = PlaylistEngine(loaded)
    playlist2 = engine2.create_playlist()
    titles = [item.get('title') for item in playlist2]
    check("Seen movie excluded",       'The Matrix' not in titles)

    # Only S01E01 of Cosmic Wanderers should appear (next unseen)
    cw_eps = [i for i in playlist if i.get('show_title') == 'Cosmic Wanderers']
    check("only one CW episode in playlist", len(cw_eps) == 1, f"got {len(cw_eps)}")
    if cw_eps:
        check("CW episode is S01E01",  cw_eps[0].get('season') == 1 and
                                        cw_eps[0].get('episode') == 1,
              f"got S{cw_eps[0].get('season')}E{cw_eps[0].get('episode')}")

    # Mark S01E01 Seen in the loaded dict and rebuild — S01E02 should now be picked
    loaded['tv_shows']['Cosmic Wanderers']['seasons']['Season 01']['episodes'][0]['status'] = 'Seen'
    engine3  = PlaylistEngine(loaded)
    playlist3 = engine3.create_playlist()
    cw_eps3 = [i for i in playlist3 if i.get('show_title') == 'Cosmic Wanderers']
    check("after S01E01 seen, S01E02 picked", len(cw_eps3) == 1 and
          cw_eps3[0].get('episode') == 2 if cw_eps3 else False,
          f"got {cw_eps3}")

finally:
    shutil.rmtree(tmpdir)

# ─────────────────────────────────────────────────────────────────────────────
print()
if failures:
    print(f"\033[31m{len(failures)} test(s) failed:\033[0m")
    for f in failures:
        print(f"  • {f}")
    sys.exit(1)
else:
    print(f"\033[32mAll tests passed.\033[0m")
    sys.exit(0)
