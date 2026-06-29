"""Self-managed USB drive lifecycle via a presence poll — no udev/udisks.

PondTV owns the mount itself. A background loop polls ``lsblk`` for a removable
data partition; when one appears we ``mount`` it ourselves with safe options,
and when it goes away (unplugged, or *mounted-but-unreadable* after the drive
browns out under load) we ``umount`` and report it gone. Because we drive the
mount synchronously, there are no async auto-mount races — the failure mode the
old pydbus/udisks2 stack was full of. Swap-without-reboot falls out for free.

The manager is engine-agnostic: it just calls ``on_mount(root)`` /
``on_unmount()`` callbacks. The manager (brain) wires those to "build channels +
resume" and "pause + show insert screen".

Key robustness point (see project history): a Pi 4 USB port can't always power a
bus-powered drive, so the drive can drop off *mid-read*. The mount then stays
present but every read returns ``EIO``. We treat "mounted but unreadable" as
drive-gone, not as a healthy empty drive — see :meth:`_is_healthy`.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Callable

# Filesystems we mount as data drives. The OS lives on ext4/mmcblk and is never
# a candidate.
SUPPORTED_FSTYPES = {"exfat", "ntfs", "vfat"}

DEFAULT_MOUNTPOINT = "/mnt/pondtv"
DEFAULT_POLL_INTERVAL = 2.0


def _run(cmd: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, check=False
    )


# Mountpoints we must never treat as a data drive, no matter the filesystem.
OS_MOUNTPOINTS = ("/", "/boot", "/boot/firmware")


def select_partition(tree: dict, fstypes: set[str] = SUPPORTED_FSTYPES) -> dict | None:
    """Pick the first USB partition with a supported FS from lsblk JSON.

    Pure (no subprocess) so the selection rules are unit-testable. The reliable
    discriminator is **transport == usb**: on a real Pi the SD card reports
    ``rm``/``hotplug`` inconsistently (mmcblk0 can be ``hotplug=1`` with a vfat
    /boot partition), so flags can't tell the OS disk from a data drive — but
    the SD card is ``tran=mmc`` and a USB stick/drive is ``tran=usb``. As
    defence-in-depth we also refuse any partition mounted at an OS path.
    """
    for disk in tree.get("blockdevices", []):
        if (disk.get("tran") or "").lower() != "usb":
            continue
        for part in disk.get("children", []) or []:
            if part.get("type") != "part":
                continue
            if (part.get("fstype") or "").lower() not in fstypes:
                continue
            if (part.get("mountpoint") or "") in OS_MOUNTPOINTS:
                continue
            return part  # has NAME, PATH, FSTYPE, MOUNTPOINT
    return None


def find_data_partition(fstypes: set[str] = SUPPORTED_FSTYPES) -> dict | None:
    """Return the first USB partition with a supported filesystem."""
    res = _run(["lsblk", "-J", "-o", "NAME,PATH,TYPE,FSTYPE,TRAN,MOUNTPOINT"])
    if res.returncode != 0:
        return None
    try:
        tree = json.loads(res.stdout)
    except json.JSONDecodeError:
        return None
    return select_partition(tree, fstypes)


class DriveManager:
    """Polls for a data drive and owns its mount/unmount lifecycle."""

    def __init__(
        self,
        on_mount: Callable[[str], None],
        on_unmount: Callable[[], None],
        mountpoint: str = DEFAULT_MOUNTPOINT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        uid: int | None = None,
        gid: int | None = None,
    ):
        self.on_mount = on_mount
        self.on_unmount = on_unmount
        self.mountpoint = mountpoint
        self.poll_interval = poll_interval
        self.uid = uid if uid is not None else os.geteuid()
        self.gid = gid if gid is not None else os.getegid()
        self._device: str | None = None  # device path we mounted, if any
        self._running = False
        self._thread: threading.Thread | None = None

    # -- mount/unmount ----------------------------------------------------

    def _mount_options(self, fstype: str) -> str:
        # Map ownership to the app user; flush only where it's valid (vfat).
        # exFAT's kernel driver has no 'flush' option (it errors); NTFS uses
        # ntfs-3g which ignores it.
        opts = [f"uid={self.uid}", f"gid={self.gid}", "noatime"]
        if fstype == "vfat":
            opts.append("flush")
        return ",".join(opts)

    def _mount(self, part: dict) -> bool:
        dev = part["path"]
        fstype = (part.get("fstype") or "").lower()
        os.makedirs(self.mountpoint, exist_ok=True)
        cmd = ["mount", "-t", fstype, "-o", self._mount_options(fstype), dev, self.mountpoint]
        res = _run(cmd)
        if res.returncode != 0:
            return False
        self._device = dev
        return True

    def _unmount(self) -> None:
        # Lazy unmount: a browned-out drive can make a normal umount block
        # forever on pending I/O, so detach the namespace immediately.
        _run(["umount", "-l", self.mountpoint])
        self._device = None

    # -- health -----------------------------------------------------------

    def _is_healthy(self) -> bool:
        """True only if the mount is actually readable (not EIO'd out)."""
        try:
            os.statvfs(self.mountpoint)
            # Touch the directory listing — an under-powered drive that dropped
            # mid-read answers statvfs but raises EIO here.
            with os.scandir(self.mountpoint) as it:
                next(it, None)
            return True
        except OSError:
            return False

    def _device_still_present(self) -> bool:
        if self._device is None:
            return False
        return os.path.exists(self._device)

    # -- poll loop --------------------------------------------------------

    def _tick(self) -> None:
        if self._device is None:
            # No drive mounted — look for one to mount.
            part = find_data_partition()
            if part is not None and self._mount(part):
                self.on_mount(self.mountpoint)
        else:
            # Drive mounted — verify it's still there and readable.
            if not self._device_still_present() or not self._is_healthy():
                self._unmount()
                self.on_unmount()

    def _loop(self) -> None:
        import traceback

        while self._running:
            try:
                self._tick()
            except Exception:  # noqa: BLE001 - the poll loop must never die
                traceback.print_exc()
            time.sleep(self.poll_interval)

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=self.poll_interval + 1)


if __name__ == "__main__":
    # Step-6 demo: watch for a drive, report mount/unmount, list channels on
    # insert. Run with privileges to mount:  sudo python3 -m pondtv.drive
    from .channels import build_channels

    def on_mount(root: str) -> None:
        print(f"[mount]   drive at {root}")
        chans = build_channels(root)
        print(f"          {len(chans)} channels, {sum(len(c.videos) for c in chans)} videos")
        for c in chans[:10]:
            print(f"            - {c.path} ({len(c.videos)})")

    def on_unmount() -> None:
        print("[unmount] drive gone — would show 'insert a drive' screen")

    print("watching for USB drives; plug/unplug to test; Ctrl-C to quit\n")
    dm = DriveManager(on_mount, on_unmount)
    dm.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        dm.stop()
        print("\nstopped")
