# PondTV

A Raspberry Pi that boots into a fullscreen video channel. Plug in a USB drive, it plays. No apps, no accounts, no menus.

Your folder structure is the channel guide. Up/down arrows switch channels, left/right scrubs. Swap USB drives like tapes — each one carries its own watch state, so a drive works on any RPI running PondTV. Pull the power when you're done.

## How it works

One long-lived [mpv](https://mpv.io) process, fullscreen over DRM/KMS — no desktop, no X11. Channel switches are a socket message, not a new process, so they're instant.

**Channels from folders.** The first folder under a top-level category is a channel; everything deeper collapses into it. Loose files in a category are one channel. Natural sort keeps episode ordering sane. The list is derived on every mount, never stored.

**State on the USB.** A `.pondtv/` directory at the drive root holds resume positions and seen flags, keyed by relative path. Writes are atomic (temp → fsync → rename) and infrequent. The RPI's OS can run on a read-only overlay root, so hard power-off can't brick either side.

Full architecture in [docs/PLAN.md](docs/PLAN.md).

## Media layout

```
USB_DRIVE/
├── Movies/
│   └── The Film/
│       ├── The Film.mkv
│       └── The Film.srt          ← same name = auto-subtitles
├── TV_Shows/
│   └── ShowName/                 ← whole show = one channel
│       ├── Season 01/
│       │   ├── S01E01.mp4
│       │   └── S01E02.mp4
│       └── Specials/
├── Ripped YT/                    ← loose files = one channel
│   ├── Video 01.mp4
│   └── Video 02.mp4
└── Selections/                   ← hand-picked mix = one channel
```

## Controls

| Key | Action |
| --- | --- |
| Space / Enter | Play / Pause |
| ← / → | Seek 10s (hold = rewind / fast-forward) |
| A / D | Previous / next video in channel |
| ↑ / ↓ | Change channel |
| Backspace | Restart video |
| S | Mark seen (skip to next) |
| T | Trailer mode (skip to unwatched) |

Input is abstracted behind an action enum — HDMI-CEC or a GPIO rotary encoder can plug in later.

## Setup

RPI 4, RPI OS Lite (64-bit), USB drive with media.

```bash
sudo apt install -y mpv python3 python3-venv python3-pip exfatprogs ntfs-3g
python3 -m venv .venv && . .venv/bin/activate && pip install -e .
sudo python3 -m pondtv
```

Install as a boot service:

```bash
sudo cp packaging/pondtv.service /etc/systemd/system/ && sudo systemctl enable --now pondtv
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for RPI setup details, running mpv from SSH, and testing without a real USB drive.

## Configuration

Optional `config.yml`, layered: defaults → machine (`/etc/pondtv/` or `~/.config/pondtv/`) → per-drive (`.pondtv/config.yml` on the USB) → env vars. Later wins. See [`packaging/config.example.yml`](packaging/config.example.yml).

```yaml
trailer_default: false
seek_seconds: 10.0
allow_quit: true
```

## Roadmap

- **Browser** — navigate the channel tree to jump to a specific video
- **Sleep timer** — clean shutdown on a timer
- **Smart-seen** — auto-mark watched when leaving near the end
- **HDMI-CEC input** — use the TV's remote
- **GPIO channel knob** — rotary encoder as a physical channel dial
- **Prebuilt OS image** — flashable SD card, ready to boot

## License

MIT
