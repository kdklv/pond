import os
import psutil
import subprocess
import re
import json
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
        """Scans block devices using lsblk, mounts them, and checks for markers."""
        try:
            cmd = ["lsblk", "--json", "-o", "NAME,TYPE,MOUNTPOINTS"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            root_device_name = None
            for device in data.get('blockdevices', []):
                if device.get('mountpoints') == ['/']:
                    root_device_name = device['name']
                    break
                if 'children' in device:
                    for part in device.get('children', []):
                        if part.get('mountpoints') == ['/']:
                            root_device_name = device['name']
                            break
                    if root_device_name:
                        break
            
            if root_device_name:
                log.info(f"Identified root block device: {root_device_name}")

            for device in data.get('blockdevices', []):
                if device.get('name') == root_device_name:
                    continue

                for part in device.get('children', []):
                    # A valid candidate is a partition with no mountpoints.
                    # lsblk shows this as a list containing a single null value.
                    if part.get('type') == 'part' and part.get('mountpoints') == [None]:
                        device_path = f"/dev/{part['name']}"
                        log.info(f"Found unmounted candidate: {device_path}")
                        mount_point = self._mount_partition(device_path)
                        
                        if mount_point and self._is_media_drive(mount_point):
                            log.info(f"Successfully mounted media drive at {mount_point}")
                            self.mounted_by_app = device_path
                            return mount_point
                        elif mount_point:
                            log.info(f"Mounted {device_path}, but not a media drive. Unmounting.")
                            self._unmount_partition(device_path)
        
        except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
            log.error(f"Failed to find or mount candidate using lsblk: {e}")

        return None

    def _mount_partition(self, device_path: str) -> str | None:
        """Mounts a partition using udisksctl."""
        try:
            cmd = ["udisksctl", "mount", "--block-device", device_path, "--no-user-interaction"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
            # Output is typically: "Mounted /dev/sdb1 at /media/user/MEDIA_NAME."
            match = re.search(r'at\s(/media/.*)\.', result.stdout)
            if match:
                return match.group(1).strip()
            log.warning(f"Could not parse mount point from udisksctl output: {result.stdout}")
            return None
        except subprocess.TimeoutExpired as e:
            log.error(f"Mount command for {device_path} timed out. Stderr: {e.stderr}")
            return None
        except subprocess.CalledProcessError as e:
            log.error(f"Failed to mount {device_path} with udisksctl. Stderr: {e.stderr}")
            return None
        except FileNotFoundError:
            log.error("udisksctl command not found. Please ensure udisks2 is installed.")
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