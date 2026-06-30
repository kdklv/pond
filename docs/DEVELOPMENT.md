# Developing PondTV on a Raspberry Pi over SSH

Workflow: edit on your laptop (or directly via SSH), run on the Pi 4 hooked to a TV.
mpv renders to the Pi's HDMI output via DRM/KMS — **you cannot see the video over SSH.**
SSH is for code + logs; the TV is your display. Plan to glance at the screen to verify.

## One-time Pi setup

- **OS:** Raspberry Pi OS Lite (64-bit). No desktop — DRM/KMS needs the console free.
- Enable SSH (`raspi-config` → Interface, or `ssh` file on the boot partition).
- Install system deps:
  ```
  sudo apt update
  sudo apt install -y mpv python3 python3-venv python3-pip \
                      exfatprogs ntfs-3g
  ```
- Add your user to `input` (for evdev keyboard) and `video` groups:
  ```
  sudo usermod -aG input,video $USER   # re-login to take effect
  ```
- Install the Python dependencies (pinned in `requirements.txt`):
  ```
  python3 -m venv .venv && . .venv/bin/activate
  pip install -r requirements.txt        # or: pip install -e ".[dev]"
  ```
  `evdev` builds a C extension, so `python3-dev` must be present (it ships with
  `python3` on Pi OS). Run the tests with `pytest`.

- Install as a service (boots straight to PondTV, restarts on crash):
  ```
  sudo cp packaging/pondtv.service /etc/systemd/system/
  sudo systemctl enable --now pondtv
  ```
  Optional config: copy `packaging/config.example.yml` to `/etc/pondtv/config.yml`
  (machine-wide) or `.pondtv/config.yml` at a USB root (per-drive).

## Running mpv on the console from SSH

mpv must own the console tty to use DRM/KMS. Options while developing:

- Stop anything holding the tty, then run the app from the console (physical keyboard or
  `sudo openvt`), **or**
- From SSH, run against the active VT: `sudo systemctl stop getty@tty1` then start the
  app so mpv grabs `/dev/dri/card*`. If DRM is "in use," another process owns the tty.

Quick smoke test (run on the Pi, watch the TV):
```
mpv --vo=gpu --gpu-context=drm --hwdec=auto /path/to/test.mp4
```

## Testing without a real USB drive

You don't need to hot-plug a drive to develop the scanner/state logic. Make a fake tree
matching the README layout and point the app at it:
```
mkdir -p ~/fakedrive/{Movies,TV_Shows,Selections}
# drop a few short sample clips in, mirror the README structure
```
For mount/poll logic, a loopback image behaves like a real removable drive:
```
truncate -s 512M /tmp/usb.img
mkfs.exfat /tmp/usb.img
sudo mount -o loop,flush /tmp/usb.img /mnt/test
```

## The overlay-root hardening (do this LAST)

`sudo raspi-config` → Performance → Overlay File System. Turn it on only after the app
is stable — while it's on, **changes to the SD card don't persist across reboot**, which
is the point in production but a nuisance during dev. Develop with it off; flip it on for
the appliance build.

## Verifying the power-cut story

Once state writes work: start playback, pull power mid-write, reboot, confirm the state
file is intact (atomic rename means you get old-or-new, never half). Repeat a few times —
this is the core promise, worth abusing.
