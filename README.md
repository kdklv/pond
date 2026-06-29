# 🪷 PondTV ⛲

> A calm, offline alternative to streaming—content flows from your own collection. Power on, and watch.

**Status:** Fully functional. Core engine running on Raspberry Pi 4s. See the [Getting Started](#getting-started) section to build and run it.

PondTV turns a Raspberry Pi 4 into a plug-and-play TV channel for your media. Think *dumb-TV*, the way dumb-phones are: no apps, no accounts, no menus to get lost in. Power on and it's already playing. Flip channels with the remote already in your hand. When you're done, kill the power like any old television—nothing to corrupt, nothing to save.

The whole library lives on a USB drive you organize yourself. Swap drives like mixtapes: one for cozy Sunday films, one for ripped YouTube channels, one for a comfort-show binge.

---

## 🐸 Features (Implemented)

- **Instant-On Playback** — boots straight into fullscreen video; channel-switching is instant over a unix socket
- **Channel Surfing** — your folders *are* the channels; flip Up/Down to surf, Left/Right to move within one
- **Smart Show Handling** — a whole series counts as one channel; natural sort keeps S01E02 before S01E10
- **Continue Where You Left Off** — per-video resume position and duration stored on the USB
- **Smart-Seen** — closing a video in its last 10 min (or last 20%) marks it watched and advances to the next
- **Next Video / Channel** — keyboard controls move forward/back through videos or jump to the next channel
- **Auto-Subtitles** — same-name `.srt`/`.ass` file beside the video loads automatically (mpv's `sub-auto`)
- **Portable Mixtapes** — watch-history lives *on the USB* in `.pondtv/state.json`, so any drive remembers its state on any Pi
- **Robust USB Handling** — detects, mounts, and unmounts drives itself; swap drives without a reboot
- **Sensible Defaults** — works out of the box; watch-state and channels are derived automatically, nothing to configure initially
- **Trailer Mode** — preview mode for trying new media; resets position and plays from the start
- **Offline First** — no internet required after setup
- **Crash-Safe State** — atomic writes (temp file → fsync → rename) so a power cut mid-save never corrupts your progress

---

## 🌀 How It Works

PondTV isn't really a video player. It's a thin **channel manager** that drives a media engine and reads your folder tree. That separation is what keeps it fast and hard to break.

### The engine: mpv

A single long-lived **mpv** process starts at boot and never restarts. It renders fullscreen straight to the screen via DRM/KMS — **no desktop, no X11** — with hardware-accelerated decode on the Pi 4, native playlists, resume positions, and automatic same-name subtitle loading.

The channel manager talks to mpv over a local socket: it sends *load this file*, *pause*, *seek*; it reads back the playback time and percent; it reacts when a file ends. Switching channels is a message down that socket — not a process launch — which is why it feels instant.

### The channel model

One rule classifies everything, with no metadata, scrapers, or filename parsing:

> **A channel is the first folder beneath a top-level category. Everything deeper collapses upward into that one channel, ordered by *natural* sort of the full path.** A category that holds loose videos directly is itself one channel.

Applied to your drive:

- `Movies/The Film/` → one channel. Drop a sequel in the same folder and it becomes the "next episode."
- `TV_Shows/ShowName/` → one channel. `Season 01/`, `Season 02/`, `Specials/` all collapse in; natural sort yields S01E01 → S01E02 → … → S02E01, so binge order and "next ep" come for free.
- `Ripped YT Channels/` (loose files) → one channel.
- `Selections/` (loose files) → one channel.

So **Up/Down** surfs the flat channel list, and **Left/Right** walks the videos inside the current channel. The quiet hero here is **natural sort** (human ordering, so `E2` comes before `E10`) — get that right and "series with specials, movies with sequels, as long as they're in order" simply works.

The channel list is **derived, never stored** — rebuilt by a quick folder walk every time a drive mounts. Cheap, always correct, nothing to corrupt.

### State lives on the USB

Because mixtapes are portable, watch-state travels *with the drive*, in a hidden `.pondtv/` folder at the USB root. Everything is keyed by **path relative to the USB root** (never absolute), so the same drive plugs into any Pi, mounts anywhere, and still knows what you've seen.

Stored per video: last position, duration, seen flag, last-watched time. Stored per channel: the "current video" pointer. From those few facts come *Continue where left off*, *Smart-seen*, and *Next-episode*.

Writes are made **crash-safe** (atomic temp-file swap — write to a temp file, `fsync`, `rename` over the original, `fsync` the dir / or SQLite in WAL mode) because the whole point is that you yank the power like a real TV — and a battery bank can cut out the same way. The Pi's own system runs on a **read-only / overlay root filesystem**, so a hard power-off can *never* corrupt the OS. The USB is the only thing written to, so writes are kept **small and infrequent** — on pause, channel change, video end, a periodic checkpoint, and shutdown — to shrink the window where a power cut could matter.

> A caveat worth stating plainly: atomic rename guarantees your state file is never half-written, but **exFAT/NTFS data drives have no journaling**, so a cut mid-write can still nick the filesystem itself. Tiny, rare writes shrink that window to near-zero; the OS, on overlay root, is never at risk.

### USB drive handling

PondTV manages drives itself with a simple **presence poll** instead of a udev/udisks auto-mount stack — that stack is where most of the corner cases and races live, so we skip it. The channel manager periodically checks for a data partition: when one appears, it mounts it (with safe flush options), walks the tree, builds channels, and resumes from saved state. When the mounted drive goes away, it pauses and shows an "insert a drive" screen.

Because PondTV owns the mount itself, the operations are synchronous and fully under its control — no reacting to async events before a filesystem has settled. You still get **swap-without-reboot**: pull one mixtape, push in another, and it reloads. exFAT/NTFS support is installed up front so ordinary big-video drives just work.

### Input is pluggable

The core only ever sees abstract actions — `PLAY_PAUSE, NEXT, PREV, CHANNEL_UP, CHANNEL_DOWN, RESTART, MARK_SEEN, BROWSE, SLEEP` — mapped from hardware by a swappable driver. The v1 driver is a **USB keyboard**: it works out of the box and is dead simple to reason about. Because input is just one driver behind that abstraction, other front-ends (an HDMI-CEC driver so the TV's own remote drives PondTV, or a GPIO rotary encoder for a literal channel knob) can be added later without touching the core — see the roadmap.

---

## 🌿 Preparing Your Media

Organize a USB drive like this. The folder structure *is* the configuration — no naming scheme to memorize, just keep things in order.

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

> 💡 **Tip:** to make a sequel feel like "the next episode" of a movie, just put both files in the same movie folder, named in order.

---

## 🎛️ Controls

Actions are abstract — in v1 they map to a USB keyboard. Other input drivers (TV remote over HDMI-CEC, a GPIO knob) can plug into the same actions later.

| Key / Button   | Action                                                                                    |
| -------------- | ----------------------------------------------------------------------------------------- |
| **Space / OK** | Play / Pause                                                                              |
| **← / →**      | Previous / Next video *within* the current channel                                        |
| **↑ / ↓**      | Change channel (Movies → that one show → the cooking videos → …) — the headline "surfing" |
| **Backspace**  | Restart current video                                                                     |
| **S**          | Mark as seen (skip to next)                                                               |
| **B**          | Open channel / file browser                                                               |
| **Sleep**      | Start the shut-off timer                                                                  |

---

## 🚀 Getting Started

**Prerequisites:**
- Raspberry Pi 4 running Raspberry Pi OS Lite (64-bit)
- USB drive formatted as exFAT or NTFS with media organized per the [Preparing Your Media](#🌿-preparing-your-media) section
- SSH access to the Pi (or direct keyboard/console access)

**Setup:**

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the complete one-time Pi setup (install mpv, Python, filesystem tools) and guidance on running over SSH.

**First run:**

```bash
# On the Pi, with a USB drive plugged in and the console/TV ready:
sudo python3 -m pondtv
```

The app will:
1. Detect and mount the USB drive
2. Walk the folder tree and build channels
3. Load the first video in the first channel
4. Restore your watch-position if you've seen it before

See [docs/PLAN.md](docs/PLAN.md) for technical architecture and design decisions.

---

## 🏊 Configuration (Future)

Configuration via `config.yml` is planned but not yet implemented. When added, it will live on the USB drive so **each mixtape carries its own settings** — making one drive "calm Sunday films" and another "chaotic YouTube rips."

Planned config options:
```yaml
# .pondtv/config.yml  (planned)
shuffle: false              # flip channels in random order
sleep_timer_minutes: 0      # 0 = off
smart_seen:
  tail_minutes: 10          # closing in the last N minutes marks seen
  tail_percent: 20          # ...or the last N percent
channel_order: auto         # auto (natural sort) | manual list
commercials: false          # inject clips from a commercials/ folder

```

For now, all settings use hardcoded defaults (smart-seen at 10 min / 20%, natural sort ordering).

---

## 🛠️ Architecture at a Glance


| Layer              | Choice                                | Why                                                                           |
| ------------------ | ------------------------------------- | ----------------------------------------------------------------------------- |
| **OS**             | Raspberry Pi OS Lite (64-bit)         | Robust, easy to build on, huge ecosystem; read-only root for power-off safety |
| **Boot**           | single `systemd` service into the app | power-on → splash → video, no login shell                                     |
| **Engine**         | mpv via DRM/KMS + JSON IPC            | fullscreen with no desktop, HW decode, playlists, subs, resume                |
| **Brain**          | "channel manager" (Python)            | walks the tree, builds channels, drives mpv over the socket                   |
| **Classification** | folder-depth + natural sort           | convention over configuration; no metadata                                    |
| **State**          | `.pondtv/` on the USB, relative paths | portable mixtapes; crash-safe atomic writes                                   |
| **USB**            | self-managed mount via presence poll  | no fragile auto-mount stack; swap drives without a reboot                      |
| **Input**          | pluggable driver → USB keyboard       | simple, works out of the box; other drivers plug into the same actions         |


---

## 💭 Roadmap (Not Yet Implemented)

The modular, pluggable design makes these additions straightforward:

**Near-term (partially wired, need implementation):**
- **Channel / File Browser** — browse/search the tree to jump directly to a specific video (action key mapped, UI not yet built)
- **Sleep Mode** — set a timer to power down the Pi cleanly (action key mapped, shutdown logic not yet built)
- **Configuration** — load `config.yml` from USB to customize smart-seen, shuffle, etc.

**Medium-term (no core changes needed):**
- **Random Mode** — shuffle a channel's playlist for that channel-flipping feel (config flag + playlist mixer)
- **Commercial Breaks** — inject clips from a `commercials/` folder between videos (mpv playlist trick)
- **Visual Effects** — runtime mpv video filters (e.g. VHS look, grain) toggled over the socket (mpv filter graph)
- **GPIO Channel Knob** — a rotary encoder for a tactile, literal channel dial (plugs into the action abstraction)

**Long-term (new input drivers):**
- **HDMI-CEC Input** — drive PondTV from the TV's own remote over HDMI (second input driver; could power down TV on Sleep)
- **Web Interface** — manage the library from a browser on the same network
- **Pre-built OS Image** — a shrunk, flashable SD-card image with PondTV ready to boot

