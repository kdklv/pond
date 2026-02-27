import os
from pydbus import SystemBus
from gi.repository.GLib import Variant
from pondtv.utils import log


class USBManager:
    """
    Handles media drive detection and mounting via direct D-Bus communication
    with the UDisks2 service.
    """

    # Folder names that identify a USB drive as a PondTV media drive.
    # Must match the top-level directories the scanner expects.
    MEDIA_MARKERS = ["Movies", "TV_Shows"]

    def __init__(self):
        self.bus = SystemBus()
        self.udisks = self.bus.get('org.freedesktop.UDisks2')
        self.mounted_by_app = None
        log.info("USBManager initialized using D-Bus.")

    def find_media_drive(self) -> str | None:
        """Scans all block devices and returns the mount path of a media drive."""
        log.info("Scanning for media drive via D-Bus...")
        try:
            objects = self.udisks.GetManagedObjects()

            for path, interfaces in objects.items():
                # We only care about block devices that expose a filesystem
                # (i.e. mountable partitions), not raw disks.
                if 'org.freedesktop.UDisks2.Filesystem' not in interfaces:
                    continue

                block = interfaces.get('org.freedesktop.UDisks2.Block', {})

                # Skip loop-back devices and anything without a backing drive.
                if block.get('ReadOnly') or not block.get('Drive'):
                    continue

                # Use the Block.Drive property (a D-Bus object path) to look up
                # the physical drive and check whether it is an MMC device
                # (i.e. the SD card that holds the OS — we never want to touch it).
                drive_path = block.get('Drive', '')
                drive_interfaces = objects.get(drive_path, {})
                drive = drive_interfaces.get('org.freedesktop.UDisks2.Drive', {})
                drive_id = drive.get('Id', '')
                if 'mmc' in drive_id.lower():
                    log.info(f"Skipping MMC device: {path} (drive id: {drive_id})")
                    continue

                # Check whether the partition is already mounted.
                mount_points = self._get_mount_points(interfaces)
                if mount_points:
                    log.info(f"Found mounted candidate: {path} at {mount_points[0]}")
                    if self._is_media_drive(mount_points[0]):
                        return mount_points[0]
                else:
                    log.info(f"Found unmounted candidate: {path}, attempting mount...")
                    mount_point = self._mount_partition(path)
                    if mount_point:
                        if self._is_media_drive(mount_point):
                            self.mounted_by_app = path
                            return mount_point
                        else:
                            # Not a media drive — unmount again.
                            self._unmount_partition(path)

        except Exception as e:
            log.error(f"Error communicating with D-Bus: {e}", exc_info=True)

        return None

    def _get_mount_points(self, interfaces: dict) -> list[str]:
        """Extracts mount point strings from a Filesystem interface dict."""
        fs = interfaces.get('org.freedesktop.UDisks2.Filesystem', {})
        raw = fs.get('MountPoints', [])
        # UDisks2 returns mount points as a list of null-terminated byte arrays.
        return [bytes(p).decode('utf-8').rstrip('\x00') for p in raw if p]

    def _is_media_drive(self, mount_path: str) -> bool:
        """Returns True if the mount path contains at least one media marker directory."""
        for marker in self.MEDIA_MARKERS:
            if os.path.isdir(os.path.join(mount_path, marker)):
                log.info(f"Found media marker '{marker}' at {mount_path}")
                return True
        return False

    def _mount_partition(self, object_path: str) -> str | None:
        """Mounts a partition via D-Bus and returns the resulting mount point."""
        try:
            fs_iface = self.bus.get(
                'org.freedesktop.UDisks2', object_path
            )['org.freedesktop.UDisks2.Filesystem']
            # auth.no_user_interaction prevents polkit prompts in headless mode
            # (allowed by the installed polkit rule).
            options = {'auth.no_user_interaction': Variant('b', True)}
            mount_point = fs_iface.Mount(options)
            log.info(f"Mounted {object_path} at {mount_point}")
            return mount_point
        except Exception as e:
            log.error(f"Failed to mount {object_path}: {e}")
            return None

    def _unmount_partition(self, object_path: str):
        """Unmounts a partition via D-Bus."""
        try:
            fs_iface = self.bus.get(
                'org.freedesktop.UDisks2', object_path
            )['org.freedesktop.UDisks2.Filesystem']
            fs_iface.Unmount({'auth.no_user_interaction': Variant('b', True)})
            log.info(f"Unmounted {object_path}")
        except Exception as e:
            log.error(f"Failed to unmount {object_path}: {e}")

    def unmount_drive(self):
        """Unmounts the drive that was mounted by this manager instance."""
        if self.mounted_by_app:
            log.info(f"Unmounting app-managed drive: {self.mounted_by_app}")
            self._unmount_partition(self.mounted_by_app)
            self.mounted_by_app = None

    def is_drive_still_connected(self, path: str) -> bool:
        """Returns True if the given mount path still exists on the filesystem."""
        return os.path.isdir(path)
