"""Unit tests for drive partition selection (pure lsblk-JSON parsing).

The key real-world lesson encoded here: on a real Pi the SD card can report
``hotplug=1`` and carry a vfat /boot partition, so removable flags can't
identify the OS disk. Selection keys off transport (usb vs mmc) instead.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pondtv.drive import select_partition  # noqa: E402


def _disk(name, tran, children):
    return {"name": name, "path": f"/dev/{name}", "type": "disk",
            "tran": tran, "children": children}


def _part(name, fstype, mountpoint=None):
    return {"name": name, "path": f"/dev/{name}", "type": "part",
            "fstype": fstype, "mountpoint": mountpoint}


class SelectPartitionTests(unittest.TestCase):
    def test_picks_usb_exfat(self):
        tree = {"blockdevices": [
            _disk("mmcblk0", "mmc", [_part("mmcblk0p2", "ext4", "/")]),  # OS disk
            _disk("sda", "usb", [_part("sda1", "exfat")]),               # USB stick
        ]}
        part = select_partition(tree)
        self.assertEqual(part["path"], "/dev/sda1")

    def test_ignores_sd_card_with_hotplug_vfat_boot(self):
        # The exact real-Pi trap: mmc transport, vfat /boot — must be ignored.
        tree = {"blockdevices": [
            _disk("mmcblk0", "mmc", [_part("mmcblk0p1", "vfat", "/boot/firmware"),
                                     _part("mmcblk0p2", "ext4", "/")]),
        ]}
        self.assertIsNone(select_partition(tree))

    def test_usb_ntfs(self):
        tree = {"blockdevices": [_disk("sda", "usb", [_part("sda1", "ntfs")])]}
        self.assertEqual(select_partition(tree)["path"], "/dev/sda1")

    def test_usb_vfat_thumb_drive(self):
        tree = {"blockdevices": [_disk("sda", "usb", [_part("sda1", "vfat")])]}
        self.assertEqual(select_partition(tree)["path"], "/dev/sda1")

    def test_unsupported_fs_skipped(self):
        tree = {"blockdevices": [_disk("sda", "usb", [_part("sda1", "ext4")])]}
        self.assertIsNone(select_partition(tree))

    def test_non_usb_transport_skipped(self):
        # An internal SATA/NVMe disk with exfat is not a data drive we manage.
        tree = {"blockdevices": [_disk("sdb", "sata", [_part("sdb1", "exfat")])]}
        self.assertIsNone(select_partition(tree))

    def test_usb_partition_at_os_mountpoint_skipped(self):
        # Defence-in-depth: even a USB partition mounted at / is never selected.
        tree = {"blockdevices": [_disk("sda", "usb", [_part("sda1", "ext4", "/")])]}
        self.assertIsNone(select_partition(tree))

    def test_no_drive(self):
        self.assertIsNone(select_partition({"blockdevices": []}))

    def test_dead_drive_no_children(self):
        # The browned-out drive: present as a disk but 0B, no partitions.
        tree = {"blockdevices": [_disk("sda", "usb", [])]}
        self.assertIsNone(select_partition(tree))

    def test_partition_without_fs_skipped(self):
        tree = {"blockdevices": [_disk("sda", "usb", [_part("sda1", None)])]}
        self.assertIsNone(select_partition(tree))


if __name__ == "__main__":
    unittest.main(verbosity=2)
