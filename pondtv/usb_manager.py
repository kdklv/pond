import os
import psutil
import subprocess
import re
from pondtv.utils import log

class USBManager:
    """
    Handles the detection, mounting, and validation of the PondTV media drive.
    """
    
    def __init__(self, markers: list = ["Movies", "Shows"]):
        self.markers = markers
        self.mounted_by_app = None  # Store the device we mounted
        log.info(f"USBManager initialized, looking for markers: {self.markers}")

    def find_media_drive(self) -> str | None:
        """
        Finds the media drive. If already mounted, returns the path. 
        If not mounted, attempts to mount it.
        """
        # 1. Check already mounted drives
        log.info("Scanning for already mounted media drives...")
        partitions = psutil.disk_partitions(all=False) # all=False is default
        for p in partitions:
            if self._is_media_drive(p.mountpoint):
                log.info(f"Found existing media drive at {p.mountpoint}")
                return p.mountpoint

        # 2. If not found, try to find and mount an unmounted one
        log.info("No mounted media drive found. Scanning for unmounted candidates...")
        return self._find_and_mount_candidate()

    def _is_media_drive(self, mount_path: str) -> bool:
        """Checks if a given path contains our media markers."""
        for marker in self.markers:
            if os.path.exists(os.path.join(mount_path, marker)):
                return True
        return False

    def _find_and_mount_candidate(self) -> str | None:
        """Scans block devices, mounts them, and checks for markers."""
        all_partitions = psutil.disk_partitions(all=True)
        mounted_devices = {p.device for p in psutil.disk_partitions(all=False)}

        # Determine the root filesystem's base device to avoid remounting it
        root_partition = next((p for p in psutil.disk_partitions(all=False) if p.mountpoint == '/'), None)
        root_base_device = None
        if root_partition:
            # e.g., /dev/mmcblk0p2 -> /dev/mmcblk0
            root_base_device = '/dev/' + os.path.basename(root_partition.device).rstrip('p0123456789')
            log.info(f"Identified root base device: {root_base_device}")

        for p in all_partitions:
            # CRITERIA FOR A VALID CANDIDATE:
            # 1. Must be a real block device (e.g., /dev/sda1), not a pseudo-fs.
            # 2. Must NOT be already mounted.
            # 3. Must NOT be part of the root filesystem disk.
            is_real_device = p.device.startswith('/dev/')
            is_mounted = p.device in mounted_devices
            is_root_fs_part = root_base_device and p.device.startswith(root_base_device)

            if not is_real_device or is_mounted or is_root_fs_part:
                continue

            log.info(f"Found unmounted candidate: {p.device} (fstype: {p.fstype})")
            mount_point = self._mount_partition(p.device)
            
            if mount_point and self._is_media_drive(mount_point):
                log.info(f"Successfully mounted media drive at {mount_point}")
                self.mounted_by_app = p.device
                return mount_point
            elif mount_point:
                # It mounted but wasn't our drive, so unmount it
                log.info(f"Mounted {p.device} at {mount_point}, but it's not a media drive. Unmounting.")
                self._unmount_partition(p.device)
        
        return None

    def _mount_partition(self, device_path: str) -> str | None:
        """Mounts a partition using udisksctl."""
        try:
            cmd = ["udisksctl", "mount", "--block-device", device_path, "--no-user-interaction"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            # Output is typically: "Mounted /dev/sdb1 at /media/user/MEDIA_NAME."
            match = re.search(r'at\s(/.*)\.', result.stdout)
            if match:
                return match.group(1).strip()
            return None
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.error(f"Failed to mount {device_path} with udisksctl: {e}")
            return None

    def _unmount_partition(self, device_path: str):
        """Unmounts a partition using udisksctl."""
        try:
            cmd = ["udisksctl", "unmount", "--block-device", device_path, "--no-user-interaction"]
            subprocess.run(cmd, capture_output=True, text=True, check=True)
            log.info(f"Successfully unmounted {device_path}.")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.error(f"Failed to unmount {device_path} with udisksctl: {e}")
            
    def unmount_drive(self):
        """Unmounts the drive that was mounted by this manager instance."""
        if self.mounted_by_app:
            log.info(f"Unmounting the drive we mounted: {self.mounted_by_app}")
            self._unmount_partition(self.mounted_by_app)
            self.mounted_by_app = None

    def is_drive_still_connected(self, path: str) -> bool:
        if not path or not os.path.exists(path):
            return False
        return path in [p.mountpoint for p in psutil.disk_partitions()]

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