"""Watch-state that lives on the USB, in ``.pondtv/state.json``.

Because mixtapes are portable, state travels *with the drive*. Everything is
keyed by **path relative to the USB root** (never absolute), so the same drive
plugs into any Pi, mounts anywhere, and still knows what you've seen — the keys
match the relative paths produced by :mod:`pondtv.channels`.

Crash-safety is the whole point: you yank the power like a real TV. Writes are
**atomic** — temp file → ``fsync`` → ``rename`` over the original → ``fsync``
the directory — so a power cut leaves you with the old *or* the new file, never
a half-written one. Loads are **tolerant**: a missing or corrupt file yields a
fresh empty state rather than crashing (the old stack's brittle validation is a
documented past failure). Writes are meant to be small and infrequent — pause,
channel change, video end, periodic checkpoint, shutdown.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_DIRNAME = ".pondtv"
STATE_FILENAME = "state.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_smart_seen(
    position: float,
    duration: float,
    tail_minutes: float = 10.0,
    tail_percent: float = 20.0,
) -> bool:
    """True if closing at ``position`` should mark the video seen.

    Smart-seen fires when the viewer was within the last ``tail_minutes`` *or*
    the last ``tail_percent`` of the runtime — whichever is more generous — so
    "I basically finished it" advances to the next episode.
    """
    if duration <= 0:
        return False
    remaining = duration - position
    if remaining <= tail_minutes * 60:
        return True
    if position >= duration * (1 - tail_percent / 100.0):
        return True
    return False


class State:
    """In-memory watch-state for one mounted drive, persisted atomically."""

    def __init__(self, usb_root: str | Path):
        self.usb_root = Path(usb_root)
        self.state_dir = self.usb_root / STATE_DIRNAME
        self.path = self.state_dir / STATE_FILENAME
        self._data: dict[str, Any] = {"videos": {}, "channels": {}}
        self._load()

    # -- loading ----------------------------------------------------------

    def _load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            return  # missing or corrupt → keep the empty default
        # Be defensive about shape; never trust the file blindly.
        if isinstance(data, dict):
            videos = data.get("videos")
            channels = data.get("channels")
            self._data["videos"] = videos if isinstance(videos, dict) else {}
            self._data["channels"] = channels if isinstance(channels, dict) else {}

    # -- video records ----------------------------------------------------

    def get_video(self, rel_path: str) -> dict[str, Any]:
        """Return the record for a video, or sane defaults if unseen."""
        return self._data["videos"].get(
            rel_path,
            {"position": 0.0, "duration": 0.0, "seen": False, "last_watched": None},
        )

    def update_video(
        self,
        rel_path: str,
        *,
        position: float | None = None,
        duration: float | None = None,
        seen: bool | None = None,
        touch: bool = True,
    ) -> None:
        """Merge fields into a video's record (in memory; call save() to persist)."""
        rec = self._data["videos"].setdefault(
            rel_path,
            {"position": 0.0, "duration": 0.0, "seen": False, "last_watched": None},
        )
        if position is not None:
            rec["position"] = float(position)
        if duration is not None:
            rec["duration"] = float(duration)
        if seen is not None:
            rec["seen"] = bool(seen)
        if touch:
            rec["last_watched"] = _utc_now_iso()

    def mark_seen(self, rel_path: str) -> None:
        # Seen videos resume from the start next time rather than the tail.
        self.update_video(rel_path, seen=True, position=0.0)

    def is_seen(self, rel_path: str) -> bool:
        return bool(self.get_video(rel_path).get("seen"))

    def resume_position(self, rel_path: str) -> float:
        return float(self.get_video(rel_path).get("position") or 0.0)

    # -- channel pointers -------------------------------------------------

    def get_channel_current(self, channel_path: str) -> str | None:
        entry = self._data["channels"].get(channel_path)
        return entry.get("current_video") if isinstance(entry, dict) else None

    def set_channel_current(self, channel_path: str, rel_path: str) -> None:
        self._data["channels"].setdefault(channel_path, {})["current_video"] = rel_path

    # -- persistence ------------------------------------------------------

    def serialize(self) -> bytes:
        """Snapshot the in-memory state to bytes ready for :meth:`write_payload`.

        Kept separate from the file write so a caller holding a lock can take a
        cheap, consistent snapshot and then do the slow fsync without the lock
        (see Manager's writer thread). Compact (no indent): the file is rewritten
        in full on every save and lands on a flaky removable drive, so fewer
        bytes means a shorter, safer fsync.
        """
        return json.dumps(self._data, separators=(",", ":")).encode("utf-8")

    def write_payload(self, payload: bytes) -> None:
        """Atomically write ``payload`` to the USB (temp → fsync → rename → fsync dir)."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_dir / (STATE_FILENAME + ".tmp")

        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.write(fd, payload)
            os.fsync(fd)  # data hits the disk before the rename
        finally:
            os.close(fd)

        os.replace(tmp, self.path)  # atomic swap on the same filesystem

        # fsync the directory so the rename itself is durable. Best-effort: the
        # rename already succeeded, and some removable filesystems (notably
        # exFAT) reject fsync on a directory fd — that must not fail the save.
        try:
            dir_fd = os.open(self.state_dir, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass

    def save(self) -> None:
        """Serialize and atomically write current state. Convenience for callers
        that don't need to separate the snapshot from the write."""
        self.write_payload(self.serialize())

    # -- introspection (mostly for tests/debug) --------------------------

    @property
    def data(self) -> dict[str, Any]:
        return self._data


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python3 -m pondtv.state <usb-root>")
        sys.exit(1)
    st = State(sys.argv[1])
    print(json.dumps(st.data, indent=2))
