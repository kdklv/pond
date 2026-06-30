# PondTV

> A calm, offline dumb-TV for your own media. Power on, and it's already playing.

PondTV turns a Raspberry Pi 4 into a single channel for a USB drive full of videos. No apps, no accounts, no menus to get lost in — power on and it's playing, flip channels with the arrow keys, kill the power when you're done like any old television. Nothing to save, nothing to corrupt.

The whole library lives on a USB stick you organize yourself. Swap drives like mixtapes: one for cozy Sunday films, one for ripped YouTube channels, one for a comfort-show binge. Each one remembers where you left off, on any Pi.

**Status** — the core runs on a Pi 4: fullscreen mpv playback, channel surfing, resume positions, self-managed USB mount, crash-safe state, a boot service, and `config.yml`. Two keys are still stubs (the browser and sleep timer); see [Roadmap](#roadmap).

## How it works

PondTV isn't really a player. It's a thin **channel manager** that drives one long-lived [mpv](https://mpv.io) process over a socket and reads your folder tree as the guide. Three ideas do all the work:

- **mpv is the engine** — a single process starts at boot and never restarts, rendering fullscreen via DRM/KMS (no desktop, no X11), with hardware decode, playlists, resume, and automatic same-name subtitles. Switching channels is a message down the socket, not a new process — that's why it's instant.
- **Folders are the channels** — one rule, no metadata or filename parsing:

  > A channel is the first folder beneath a top-level category; everything deeper collapses up into it. A category with loose videos in it is itself one channel.

  **Natural sort** keeps `S01E02` before `S01E10` and Season 01 before Season 02. The list is derived fresh on every mount — never stored, nothing to corrupt.

- **State rides on the USB** — in a hidden `.pondtv/` at the drive root, keyed by path *relative* to the USB (so a drive works on any Pi). Writes are atomic (temp → fsync → rename) and rare, because the whole point is you yank the power like a real TV. The Pi's OS can run on a read-only overlay root, so a hard power-off can't brick it either.

Full architecture and design rationale in [docs/PLAN.md](docs/PLAN.md).

## Preparing your media

The folder structure *is* the configuration — no naming scheme to memorize, just keep things in order.

```
USB_DRIVE/
├── Movies/
│   └── The Film/
│       ├── The Film.mkv
│       └── The Film.srt          ← same name = auto-subtitles
├── TV_Shows/
│   └── ShowName/                 ← whole show = one channel
│       ├── Season 01/
│       │   ├── ShowName - S01E01.mp4
│       │   └── ShowName - S01E02.mp4
│       └── Specials/
│           └── ShowName - Special.mp4
├── Ripped YT Channels/           ← loose files = one channel
│   ├── Video 01.mp4
│   └── Video 02.mp4
└── Selections/                   ← a hand-picked mixtape channel
    ├── Clip A.mp4
    └── Clip B.mp4
```

> Tip: to make a sequel feel like "the next episode" of a movie, put both files in the same movie folder, named in order.

## Controls

Actions are abstract; in v1 they map to a USB keyboard. Other drivers (the TV remote over HDMI-CEC, a GPIO knob) can plug into the same actions later.

| Key | Action |
| --- | --- |
| **Space / Enter** | Play / Pause |
| **← / →** | Seek 10s (hold = rewind / fast-forward) |
| **A / D** | Previous / next video within the channel |
| **↑ / ↓** | Change channel — the headline "surfing" |
| **Backspace** | Restart current video |
| **S** | Mark as seen (skip to next) |
| **T** | Toggle trailer mode (catch fresh videos mid-broadcast) |
| **B** | Browser *(stub)* |
| **Sleep / Power** | Shut-off timer *(stub)* |
| **Esc / Q** | Quit (disabled on a deployed appliance) |

## Getting started

You need a Raspberry Pi 4 running Pi OS Lite (64-bit), a USB drive with media organized as above, and SSH or a console keyboard.

```bash
sudo apt install -y mpv python3 python3-venv python3-pip exfatprogs ntfs-3g
python3 -m venv .venv && . .venv/bin/activate && pip install -e .

# run it (mpv renders to the Pi's HDMI, not SSH — watch the TV):
sudo python3 -m pondtv
```

To boot straight into PondTV and restart on crash, install the service:

```bash
sudo cp packaging/pondtv.service /etc/systemd/system/ && sudo systemctl enable --now pondtv
```

Pi setup, running mpv on the console from SSH, and testing without a real USB drive are covered in [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Configuration

Optional `config.yml`, loaded in order (later wins): built-in defaults → `/etc/pondtv/config.yml` or `~/.config/pondtv/config.yml` (machine) → `.pondtv/config.yml` at the USB root (per-drive, travels with the mixtape) → environment. Unknown keys are ignored, and a missing or broken file falls back to the layer below. See [`packaging/config.example.yml`](packaging/config.example.yml).

```yaml
# .pondtv/config.yml  (per-drive — travels with the mixtape)
trailer_default: false     # start in flip-through mode
seek_seconds: 10.0         # ←/→ scrub step
allow_quit: true           # off for kiosks (the service sets PONDTV_ALLOW_QUIT=0)
```

## Roadmap

The pluggable design keeps these mostly additive:

- **Browser** — browse/search the tree to jump to a specific video (key mapped, UI not built).
- **Sleep timer** — power the Pi down cleanly on a timer (key mapped, logic not built).
- **Smart-seen on close** — wire the existing `is_smart_seen` helper into transitions so leaving near the end marks a video watched.
- **Random mode / commercial breaks / visual filters** — mpv playlist and filter tricks.
- **GPIO channel knob** — a rotary encoder as a literal channel dial.
- **HDMI-CEC input** — drive it from the TV's own remote.
- **Prebuilt OS image** — a flashable SD card with PondTV ready to boot.

## License

MIT — see [LICENSE](LICENSE).
