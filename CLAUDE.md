# PondTV — context for Claude

PondTV turns a Raspberry Pi 4 into a plug-and-play "dumb-TV" channel for a USB media
library. Power on → fullscreen video; arrow keys surf channels. Read the
[README](README.md) for the full vision and [docs/PLAN.md](docs/PLAN.md) for the
implementation plan. **This repo is mid-restart: the spec and plan exist, the
implementation does not yet.** An earlier Python implementation was removed (see git
history) — don't resurrect it wholesale; the architecture has changed.

## Locked-in decisions (don't relitigate without being asked)

- **Keyboard-only input for v1.** HDMI-CEC and GPIO are future drivers behind the same
  abstract `Action` enum. Use **`evdev`**, not `pynput` (pynput needs X11; the Pi runs
  headless).
- **Self-managed mount via a presence poll** — NOT udev/udisks2 auto-mount. The old
  stack's `pydbus`/`udisks2` path caused the mount race conditions visible in git
  history. The manager owns `mount`/`umount` synchronously. Swap drives without a reboot.
- **mpv is the engine**, one long-lived process, DRM/KMS (no X11/desktop), driven over a
  unix-socket JSON IPC. Prefer a small raw-socket client over `python-mpv`/`libmpv-dev`.
- **State lives on the USB** in `.pondtv/`, keyed by path **relative** to the USB root.
  Writes are **atomic** (temp → fsync → rename → fsync dir) and **infrequent** (pause,
  channel change, video end, periodic checkpoint, shutdown).
- **Read-only/overlay root** protects the OS from power cuts (battery-bank use). exFAT/
  NTFS data drives have no journaling, so corruption protection there is "bounded," not
  absolute — keep writes tiny and rare.
- **Channels are derived, never stored:** channel = first folder under a top-level
  category, deeper paths collapse upward, ordered by **natural sort** of the full
  relative path. No metadata/scrapers/filename parsing.

## Dev environment

Built and run on a Pi 4 over SSH. **mpv renders to the Pi's HDMI, not over SSH** — verify
video on the actual TV. See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for Pi setup,
running mpv on the console from SSH, and testing without a real USB drive.

## Build order

See [docs/PLAN.md](docs/PLAN.md). Roughly: mpv-boots-a-file → IPC client → channel walk +
natural sort → keyboard/actions → USB state → presence-poll mount → hardening → polish.
Steps build independently; verify each on the Pi before moving on.
