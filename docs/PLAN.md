# PondTV — Implementation Plan

This is the build-time companion to the [README](../README.md). The README is the
*what/why* (the spec); this is the *how* (modules, interfaces, build order). Decisions
already locked in: **keyboard-only input** for v1, **self-managed mount via presence
poll** (no udev/udisks auto-mount), **read-only overlay root + atomic USB writes**.

---

## Module breakdown

A thin channel manager around a long-lived mpv process. Suggested layout:

```
pondtv/
├── __main__.py        # entrypoint: wire everything, run the main loop
├── config.py          # load/merge config.yml (defaults + per-drive overrides)
├── mpv_ipc.py         # JSON-IPC client over the mpv unix socket
├── channels.py        # folder walk → channel list (folder-depth + natural sort)
├── state.py           # read/write .pondtv/ state, atomic writes, relative-path keys
├── drive.py           # presence poll, mount/unmount, "insert a drive" lifecycle
├── input_kbd.py       # evdev keyboard → abstract Action enum
├── actions.py         # Action enum + the dispatch that maps Action → manager method
└── manager.py         # the brain: holds current channel/video, reacts to mpv events
```

Keep input behind `actions.Action` so an HDMI-CEC/GPIO driver can be added later
without touching the core (see README roadmap).

---

## mpv: launch + IPC

Launch one mpv at boot, render via DRM/KMS (no X), expose a control socket:

```
mpv --idle=yes --force-window=no \
    --vo=gpu --gpu-context=drm --hwdec=auto \
    --input-ipc-server=/tmp/pondtv-mpv.sock \
    --sub-auto=fuzzy --keep-open=yes
```

Talk to it over the unix socket with newline-delimited JSON. Rolling a ~50-line client
(`mpv_ipc.py`) avoids the `libmpv-dev` / `python-mpv` version coupling and matches the
"talks to mpv over a socket" design. Command set the manager needs:

| Intent              | IPC                                                            |
| ------------------- | ------------------------------------------------------------- |
| Load a file         | `{"command":["loadfile","<path>","replace"]}`                 |
| Play / pause        | `{"command":["set_property","pause",true/false]}`             |
| Seek to resume pos  | `{"command":["set_property","time-pos",<seconds>]}`           |
| Restart             | `{"command":["seek",0,"absolute"]}`                           |
| Read position       | `{"command":["get_property","time-pos"]}`                     |
| Read duration       | `{"command":["get_property","duration"]}`                     |
| Read percent        | `{"command":["get_property","percent-pos"]}`                  |
| React to file end   | observe `eof-reached` / listen for `end-file` event           |
| Show OSD text       | `{"command":["show-text","<msg>",<ms>]}`                      |

Observe properties (`observe_property`) rather than polling where you can; the socket
pushes events asynchronously. **Watchdog:** if mpv dies, systemd restarts it and the
manager must reconnect to the socket and reload the current video.

---

## Channel model (the one rule)

> A channel = the first folder beneath a top-level category. Everything deeper collapses
> upward into that one channel, ordered by **natural sort** of the full relative path. A
> category holding loose video files directly is itself one channel.

- Walk only video extensions (`.mkv .mp4 .avi .mov .m4v .webm` …).
- **Natural sort is the quiet hero** — `E2` before `E10`. Sort on the full relative path
  so `Season 01/.../S01E02` orders before `Season 02/...`. Write a unit test for this
  first; it's the thing most likely to be subtly wrong.
- Channel list is **derived, never stored** — rebuild on every mount.
- Subtitles: same-basename `.srt`/`.ass` beside the video (mpv `--sub-auto` handles it).

---

## State schema (`.pondtv/` at USB root)

Keyed by **path relative to the USB root** (never absolute) so a drive works on any Pi.
Atomic writes: write `*.tmp` → `fsync` → `rename` over original → `fsync` dir. Either a
single JSON file or SQLite-WAL. Write only on: pause, channel change, video end,
periodic checkpoint (~30–60s), shutdown.

```jsonc
{
  "videos": {
    "TV_Shows/ShowName/Season 01/S01E01.mkv": {
      "position": 1234.5, "duration": 2400.0,
      "seen": false, "last_watched": "2026-06-25T20:00:00Z"
    }
  },
  "channels": {
    "TV_Shows/ShowName": { "current_video": "TV_Shows/ShowName/Season 01/S01E01.mkv" }
  }
}
```

From these few facts come *Continue where left off*, *Smart-seen* (closing in last
`tail_minutes` or `tail_percent` marks seen + advances), and *Next-episode*.

---

## Drive handling (presence poll, no udev)

The manager owns the mount, so it's all synchronous and race-free:

1. Poll for a candidate data partition (e.g. via `lsblk`/`/proc/mounts`, or watch a
   mountpoint). Debounce.
2. On appear: `mount` it ourselves with safe flush options
   (`-o flush` for exFAT/vfat), read `config.yml`, walk tree, build channels, resume.
3. On disappear: pause, unmount cleanly if still mounted, show "insert a drive" screen.
4. Swap-without-reboot falls out for free. Install exFAT/NTFS support up front.

Drop `pydbus` / `udisks2` / `python-gi` from the old stack — they're the source of the
auto-mount races in the old git history.

---

## Input (keyboard, headless)

`pynput` (old stack) needs X11 — **won't work on a no-desktop tty.** Use **`python-evdev`**
to read the keyboard device from `/dev/input` directly; it's headless-safe. Map keys →
`Action`:

```
SPACE→PLAY_PAUSE  ←/→→PREV/NEXT  ↑/↓→CHANNEL_DOWN/CHANNEL_UP
BACKSPACE→RESTART  S→MARK_SEEN  B→BROWSE  (sleep key)→SLEEP
```

---

## Dependencies (proposed, trimmed from old stack)

```
pyyaml          # config.yml
evdev           # headless keyboard input  (replaces pynput)
# mpv IPC: raw unix-socket JSON client, no python-mpv/libmpv-dev needed
# mount:   subprocess to `mount`/`umount`, no pydbus/udisks2
```

System packages on the Pi: `mpv`, `python3`, `exfatprogs`/`exfat-fuse`, `ntfs-3g`.

---

## Build order (each step is independently runnable)

1. **mpv boots fullscreen** via systemd, plays one hardcoded file (proves DRM/KMS + HW decode).
2. **`mpv_ipc.py`** — connect, load/pause/seek, read position, catch end-of-file.
3. **`channels.py`** — folder walk → channel list + natural sort (+ unit tests).
4. **`input_kbd.py` + `actions.py`** — keyboard drives PREV/NEXT/CHANNEL up-down/etc.
5. **`state.py`** — atomic read/write on USB; resume, smart-seen, next-episode pointer.
6. **`drive.py`** — presence poll, self-mount, insert screen, swap-without-reboot.
7. **Hardening** — read-only overlay root, mpv watchdog, bounded write triggers.
8. **Polish** — browser overlay, sleep timer, splash screen.

Steps 1–5 give a usable PondTV on a fixed drive; 6–8 make it appliance-grade.

---

## Known gotchas (carry these forward)

- **mpv DRM output renders on the Pi's HDMI/console, not over SSH.** You develop logic
  over SSH but must watch the actual TV to verify video. Run the app on the console tty.
- **evdev, not pynput** — pynput silently needs a display.
- **exFAT/NTFS have no journaling** — atomic rename protects your file, not the FS
  metadata. Keep writes tiny + rare.
- **mpv can die on a bad codec/file** — needs systemd restart + manager reconnect.
- **Natural sort across season folders** — sort the full relative path, test it early.
