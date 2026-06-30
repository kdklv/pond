"""Derive the channel list from the USB folder tree — no metadata or scraping.

> A channel is the first folder beneath a top-level category; everything deeper
> collapses upward into it. A category holding loose video files directly is
> itself one channel.

Channels and their videos are ordered by *natural* sort of the full relative
path (so ``Season 01/…/S01E02`` precedes ``Season 02/…/S02E01``, and ``E2``
precedes ``E10``). The list is derived on every mount, never stored; keys are
paths relative to the USB root, POSIX-style, so a drive works on any Pi.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# Recognised video containers. Lowercase; matched case-insensitively.
VIDEO_EXTS = {
    ".mkv",
    ".mp4",
    ".avi",
    ".mov",
    ".m4v",
    ".webm",
    ".mpg",
    ".mpeg",
    ".ts",
    ".flv",
    ".wmv",
}


@dataclass
class Channel:
    """One surfable channel: a name, its relative-path key, and its videos."""

    name: str  # display name (the folder name)
    path: str  # relative path key from the USB root, POSIX-style
    videos: list[str] = field(default_factory=list)  # relative paths, natural-sorted


def natural_key(text: str) -> list:
    """Sort key for human/natural ordering: ``E2`` before ``E10``.

    Splits a string into digit and non-digit runs, comparing digit runs
    numerically and text runs case-insensitively. Applied to the full relative
    path so that ``Season 01/…`` orders before ``Season 02/…``.
    """
    return [
        int(token) if token.isdigit() else token.lower()
        for token in re.split(r"(\d+)", text)
    ]


def _has_video_ext(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in VIDEO_EXTS


def _is_hidden(name: str) -> bool:
    # Skip dotfiles/dirs (.pondtv state dir, .Trash-*, macOS ._ files, etc.).
    return name.startswith(".")


def _subdirs(folder: Path) -> list[os.DirEntry]:
    """Immediate, non-hidden subdirectories of ``folder``; [] if unreadable."""
    out = []
    try:
        with os.scandir(folder) as it:
            for entry in it:
                if _is_hidden(entry.name):
                    continue
                try:
                    if entry.is_dir():
                        out.append(entry)
                except OSError:
                    continue  # unreadable entry — skip it, don't crash
    except OSError:
        pass
    return out


def _videos_under(folder: Path, root: Path) -> list[str]:
    """Every video at any depth beneath ``folder``, as natural-sorted rel keys.

    Uses os.walk so a single unreadable file or directory (an I/O error on a
    flaky USB drive, a corrupt exFAT entry) is skipped rather than crashing the
    whole walk — real-world drives always have a weird entry somewhere.
    """
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(folder, onerror=lambda _e: None):
        dirnames[:] = [d for d in dirnames if not _is_hidden(d)]
        for name in filenames:
            if _is_hidden(name) or not _has_video_ext(name):
                continue
            found.append(Path(dirpath, name).relative_to(root).as_posix())
    found.sort(key=natural_key)
    return found


def _scan_category(folder: Path, root: Path) -> tuple[list[str], list[os.DirEntry]]:
    """One scandir pass over a category: its loose videos and its subdirectories.

    Returns ``(loose_video_rel_keys_sorted, subdir_entries)``. Folding both into a
    single pass avoids scanning the category directory twice (once for files, once
    for folders), which matters on slow USB media.
    """
    loose: list[str] = []
    subdirs: list[os.DirEntry] = []
    try:
        with os.scandir(folder) as it:
            for entry in it:
                if _is_hidden(entry.name):
                    continue
                try:
                    if entry.is_dir():
                        subdirs.append(entry)
                    elif _has_video_ext(entry.name) and entry.is_file():
                        loose.append(Path(entry.path).relative_to(root).as_posix())
                except OSError:
                    continue  # unreadable entry — skip it, don't crash
    except OSError:
        pass
    loose.sort(key=natural_key)
    return loose, subdirs


def build_channels(root: str | Path) -> list[Channel]:
    """Walk ``root`` and return the derived, natural-sorted channel list."""
    root = Path(root)
    channels: list[Channel] = []

    for category in _subdirs(root):
        cat_path = Path(category.path)
        loose, cat_subdirs = _scan_category(cat_path, root)

        # Loose files directly under the category → one channel (the category).
        if loose:
            channels.append(
                Channel(
                    name=category.name,
                    path=cat_path.relative_to(root).as_posix(),
                    videos=loose,
                )
            )

        # Each immediate subfolder → one channel collapsing everything beneath it.
        for sub in cat_subdirs:
            sub_path = Path(sub.path)
            videos = _videos_under(sub_path, root)
            if videos:
                channels.append(
                    Channel(
                        name=sub.name,
                        path=sub_path.relative_to(root).as_posix(),
                        videos=videos,
                    )
                )

    channels.sort(key=lambda c: natural_key(c.path))
    return channels


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python3 -m pondtv.channels <usb-root>")
        sys.exit(1)
    for i, ch in enumerate(build_channels(sys.argv[1])):
        print(f"[{i}] {ch.path}  ({len(ch.videos)} videos)")
        for v in ch.videos:
            print(f"      {v}")
