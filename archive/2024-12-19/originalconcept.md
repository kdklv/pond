# 🌊 PondTV

> A zen-inspired, offline alternative to streaming services - where content flows like a peaceful pond, not a rushing stream.

PondTV transforms your Raspberry Pi into a plug-and-play, old-school TV channel experience for your personal movie and show collection. Power on and relax—no menus, no decisions, just calm, shuffled playback from your USB drive.

---

## 1. Overview

PondTV is designed to combat choice paralysis and streaming fatigue by offering a simple, offline, and minimal-interaction media experience. It boots directly into playback, shuffles your movies and TV episodes, and lets you "channel surf" with a single button—just like classic television, but with your own library.

---

## 2. Core Philosophy

- Combat choice paralysis and streaming fatigue
- Create a calm, "lean-back" viewing experience
- Maintain simplicity through minimal user interaction
- Operate completely offline from local storage

---

## 3. Features

- **Instant-On Playback:** Boots straight into fullscreen media playback.
- **Channel Surfing:** Simple input to switch to another random movie or the next unseen episode of a series.
- **Offline Operation:** All media and metadata are local—no internet required.
- **Series Awareness:** Always plays the next unseen episode for each series; movies are shuffled individually.
- **"Seen" Status Tracking:** Mark content as seen (auto or manual), so only unseen items play by default.
- **Minimal UI:** Focus on content, not menus. Optional splash screens or info overlays.
- **Auto-Discovery:** Automatically scans and catalogs your media collection.
- **Playback Controls:** Basic on-screen controls for play/pause and subtitle adjustment.

---

## 4. Hardware Requirements

- **Raspberry Pi:** Model 4 recommended (3B+ minimum)
- **SD Card:** (for OS, 32GB+ recommended)
- **USB Drive:** (for media files & CSV database, 64GB+ recommended)
- **HDMI Display:** (TV or monitor)
- **Input Device:** USB keyboard, IR remote (via FLIRC), or GPIO buttons
- **Power Supply:** Official Pi power supply (suitable for your Pi, e.g., 5V/3A for Pi 4)
- **Optional:** Retro case, speakers, IR sensor

---

## 5. Software Stack

- **OS:** Raspberry Pi OS Lite (or similar minimal Linux)
- **Media Player:** `mpv` (preferred), `cvlc` (VLC CLI), or OMXPlayer
- **Core Script:** Python (with `pandas` or `csv`), or Bash for advanced users
- **Autostart:** systemd service or `.bashrc` autologin script
- **Database:** YAML file for structured data (see Media Organization & Metadata)
- **Optional:** LIRC for IR remote support

---

## 6. Media Organization & Metadata

**USB Drive Structure Example:**
```
USB_DRIVE/
├── Movies/  # Or 'movies/'
│   └── Movie Title (Year).mkv
├── TV_Shows/ # Or 'shows/'
│   └── ShowName/
│       └── Season 01/
│           └── ShowName - S01E01 - EpisodeTitle.mp4
│           └── ShowName - S01E02 - AnotherEpisode.mp4
└── media_library.yml # Media database in YAML format
```
*Note: Consistency in naming (e.g., `Movies/` vs `movies/`, `media_library.csv` vs `media.csv`) is important for script functionality. Choose one and stick to it.*

**YAML Format Example (`media_library.yml`):**
```yaml
movies:
  - filepath: "Movies/Inception (2010).mkv"
    title: "Inception"
    year: 2010
    status: "Unseen"
    resume_position: null
    last_watched: null
    subtitles: ["Movies/Inception (2010).srt"]

series:
  - series_name: "The Office"
    episodes:
      - filepath: "TV_Shows/The Office/Season 01/The Office - S01E01 - Pilot.mp4"
        title: "Pilot"
        season: 1
        episode: 1
        status: "Unseen"
        resume_position: null
        last_watched: null
```
- **Structure:**
  - `movies`: List of movie objects with title, year, filepath, and status tracking
  - `series`: List of series objects, each containing episodes with season/episode numbers
  - `status`: "Unseen" or "Seen" (tracks playback status)
  - `resume_position`: Future feature for resuming playback (currently null)

---

## 7. Playback Logic

1.  **Boot & Mount:** Pi boots, script auto-starts, mounts USB, finds `media_library.yml`.
2.  **Parse Database:** Reads YAML database, filters out `Seen` items.
3.  **Playlist Compilation:**
    *   For movies: all unseen movies are eligible.
    *   For series: only the next unseen episode per series is eligible (e.g., if S01E03 is unseen, S01E04 won't be added until S01E03 is played).
4.  **Shuffle & Play:** Randomly selects an item from the compiled pool and launches the media player in fullscreen.
5.  **Channel Surfing:** User input (e.g., button press) triggers playback of the next randomly selected item (another movie or the next unseen episode from a *different* series to encourage variety).
6.  **Seen Status Update:** After playback completes (or via manual user input), the item's `Status` in the YAML database is updated to `Seen`.

---

## 8. User Interaction

- **Channel Up/Down (or Next Button):** Skips to the next random movie or the next unseen episode from a different series.
- **Mark as Seen:** Can be automatic after a configurable percentage of playback or manually triggered by user input.
- **Minimal On-Screen Info (Optional):** Brief overlay for title, episode, or status when a new item starts or on demand.
- **No Menus:** Designed for a "lean-back," zero-decision experience.

---

## 9. Setup Guide (Quick Start)

1.  **Prepare Hardware:** Assemble Raspberry Pi, connect display, input device, and USB drive.
2.  **Install OS & Software:**
    *   Flash Raspberry Pi OS Lite to the SD card.
    *   Boot the Pi, connect to the internet (for initial setup).
    *   Install necessary software: `sudo apt update && sudo apt install mpv python3-pandas` (or `cvlc` if preferred).
3.  **Organize Media:**
    *   Copy your movies and TV shows to the USB drive, following your chosen directory structure (see Section 6).
    *   The `media_library.yml` database will be automatically created when you first run PondTV.
4.  **Configure Autostart:**
    *   Write your core Python script for PondTV logic.
    *   Set up your script to run automatically on boot (e.g., using a systemd service or by adding it to `/etc/rc.local` or a user's `.bashrc` / `.profile` for autologin).
5.  **Plug & Play:** Insert the prepared USB drive, power on the Pi, and PondTV should start playing your media!

---


## 11. Future Ideas

- **Genre/Playlist "Channels":** Allow filtering or selection by genre or pre-defined playlists.
- **Upcoming Videos Display:** Show a preview of the next 3 videos in the queue.
- **Full Library View:** Browse your entire cinema and TV show library.
- **Time-Based Scheduling:** Simulate a TV schedule (e.g., cartoons in the morning, movies at night).
- **Visual Filters:** Optional aesthetic filters (e.g., CRT scanlines, black & white).
- **Web Interface:** For easier library management and settings configuration.
- **Multi-Device Sync:** Sync "seen" status across multiple PondTV instances (more complex).
- **Preview Clips:** Optional short previews before full playback.
- **Minimal UI Enhancements:** Show "now playing" info, progress bar, or artwork subtly.
- **Settings File:** For customizing playback behavior, preview length, UI elements, etc.
- **Multiple USB Support:** Ability to scan and use media from multiple connected USB drives.
- **Performance Optimizations:** Further improvements to boot speed and script efficiency.

---

**PondTV** — Embrace the calm of the pond. Enjoy your own personal TV channel, offline and effortless.