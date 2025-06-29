import os
import time
from pydbus import SystemBus
from gi.repository.GLib import Variant
from pondtv.utils import log

class USBManager:
    """
    Handles media drive detection and mounting via direct D-Bus communication
    with the UDisks2 service.
    """
    def __init__(self, markers: list = ["Movies", "Shows"]):
        self.markers = markers
        self.bus = SystemBus()
        self.udisks = self.bus.get('org.freedesktop.UDisks2')
        self.mounted_by_app = None
        log.info("USBManager initialized using D-Bus.")

    def find_media_drive(self) -> str | None:
        """Finds the media drive, mounting it if necessary."""
        log.info("Scanning for media drive via D-Bus...")
        try:
            objects = self.udisks.GetManagedObjects()
            for path, interfaces in objects.items():
                # A block device with a partition table is a physical disk.
                if 'org.freedesktop.UDisks2.PartitionTable' in interfaces:
                    # Now check its partitions.
                    for part_path, part_interfaces in objects.items():
                        partition = part_interfaces.get('org.freedesktop.UDisks2.Partition')
                        if partition and partition['Table'] == path:
                            # This partition belongs to our current disk.
                            drive = part_interfaces.get('org.freedesktop.UDisks2.Drive')
                            # Ignore the OS drive (e.g., SD card reader)
                            if drive and drive.get('Id') and 'mmc' in drive['Id']:
                                continue
                            
                            # Check if it's already mounted
                            mount_points = self._get_mount_points(part_interfaces)
                            if mount_points:
                                log.info(f"Found already mounted candidate: {part_path}")
                                if self._is_media_drive(mount_points[0]):
                                    return mount_points[0]
                            else:
                                # Not mounted, so let's try to mount it.
                                log.info(f"Found unmounted candidate: {part_path}")
                                mount_point = self._mount_partition(part_path)
                                if mount_point and self._is_media_drive(mount_point):
                                    self.mounted_by_app = part_path
                                    return mount_point
                                elif mount_point:
                                    self._unmount_partition(part_path)
        except Exception as e:
            log.error(f"Error communicating with D-Bus: {e}", exc_info=True)
        return None

    def _get_mount_points(self, interfaces: dict) -> list[str]:
        """Gets mount points from the Filesystem interface."""
        fs = interfaces.get('org.freedesktop.UDisks2.Filesystem')
        if fs and fs['MountPoints']:
            # The D-Bus call returns mount points as a list of byte arrays (aay).
            # Each path is often null-terminated, so we must convert to bytes,
            # decode, and strip trailing nulls.
            return [bytes(p).decode('utf-8').rstrip('\x00') for p in fs['MountPoints']]
        return []

    def _is_media_drive(self, mount_path: str) -> bool:
        """Checks if a mount path contains our media markers."""
        for marker in self.markers:
            if os.path.exists(os.path.join(mount_path, marker)):
                log.info(f"Found media marker '{marker}' at {mount_path}")
                return True
        return False

    def _mount_partition(self, object_path: str) -> str | None:
        """Mounts a partition using its D-Bus object path."""
        try:
            fs_interface = self.bus.get('org.freedesktop.UDisks2', object_path)['org.freedesktop.UDisks2.Filesystem']
            # Add 'auth.no_user_interaction' to prevent auth prompts that
            # would fail in a headless service environment. This is allowed
            # by the polkit rule. The value must be a GLib.Variant.
            mount_options = {'auth.no_user_interaction': Variant('b', True)}
            mount_path = fs_interface.Mount(mount_options)
            log.info(f"Successfully mounted {object_path} at {mount_path}")
            return mount_path
        except Exception as e:
            log.error(f"Failed to mount {object_path}: {e}")
            return None

    def _unmount_partition(self, object_path: str):
        """Unmounts a partition using its D-Bus object path."""
        try:
            fs_interface = self.bus.get('org.freedesktop.UDisks2', object_path)['org.freedesktop.UDisks2.Filesystem']
            fs_interface.Unmount({})
            log.info(f"Successfully unmounted {object_path}")
        except Exception as e:
            log.error(f"Failed to unmount {object_path} via D-Bus: {e}")

    def unmount_drive(self):
        """Unmounts the drive that was mounted by this manager."""
        if self.mounted_by_app:
            log.info(f"Unmounting D-Bus managed drive: {self.mounted_by_app}")
            self._unmount_partition(self.mounted_by_app)
            self.mounted_by_app = None

    def is_drive_still_connected(self, path: str) -> bool:
        """Checks if a drive is still connected by checking its mount point."""
        # A simple os.path check is sufficient with D-Bus, as udisks
        # cleans up mount points on disconnect.
        return os.path.exists(path)

    def _on_interfaces_added(self, path, interfaces):
        log.info(f"Interfaces added at {path}")

if __name__ == '__main__':
    # Test script for the USBManager
    log.info("--- Running USBManager Test ---")
    
    manager = USBManager()
    media_drive_path = manager.find_media_drive()
    
    if media_drive_path:
        log.info(f"Success! Media drive found: {media_drive_path}")
    else:
        log.warning("Test complete, but no media drive was found.")
        log.info("To test properly, connect a USB drive containing a 'Movies' or 'Shows' directory.")
        
    log.info("--- Test Complete ---") 