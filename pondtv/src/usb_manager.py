import os
import psutil
import platform
from .utils import log

class USBManager:
    """Handles the detection and validation of the PondTV media drive."""
    
    def __init__(self, marker: str = "Movies"):
        """
        Initializes the USBManager.
        
        Args:
            marker: A file or directory name to look for to identify the correct
                    media drive. Defaults to "Movies".
        """
        self.marker = marker
        self.system = platform.system().lower()
        log.info(f"USBManager initialized for {self.system}, looking for marker: '{self.marker}'")

    def find_media_drive(self) -> str | None:
        """
        Scans all connected drives to find the correct media drive.
        
        It identifies the drive by checking for the existence of the marker
        (e.g., a "Movies" directory).
        
        Returns:
            The mount path of the media drive if found, otherwise None.
        """
        log.info("Scanning for media drive...")
        partitions = psutil.disk_partitions()
        
        for p in partitions:
            # Skip system partitions based on filesystem type and mount options
            if self._is_system_partition(p):
                continue
                
            log.info(f"Checking potential drive at {p.mountpoint}...")
            
            # Check if the drive is accessible and contains our marker
            if self._check_drive_for_marker(p.mountpoint):
                log.info(f"PondTV media drive found at: {p.mountpoint}")
                return p.mountpoint
                
        log.warning("No PondTV media drive found.")
        return None

    def _is_system_partition(self, partition) -> bool:
        """
        Determines if a partition is likely a system partition that should be skipped.
        
        Args:
            partition: psutil partition object
            
        Returns:
            True if partition should be skipped, False otherwise
        """
        mountpoint = partition.mountpoint.lower()
        fstype = partition.fstype.lower()
        opts = partition.opts.lower()
        
        # Skip common system partitions
        system_mounts = {
            'linux': ['/boot', '/sys', '/proc', '/dev', '/run', '/tmp', '/var/snap'],
            'darwin': ['/system', '/private', '/dev', '/cores'],
            'windows': []  # Windows drive letters are usually fine to check
        }
        
        # Check for system mount points
        for sys_mount in system_mounts.get(self.system, []):
            if mountpoint.startswith(sys_mount):
                log.debug(f"Skipping system partition: {mountpoint}")
                return True
        
        # Skip filesystems that are definitely not media drives
        system_fstypes = ['proc', 'sysfs', 'tmpfs', 'devtmpfs', 'devpts', 'cgroup', 'pstore']
        if fstype in system_fstypes:
            log.debug(f"Skipping system filesystem: {fstype}")
            return True
            
        # Skip read-only mounts (unless it's a CD/DVD which might be intentional)
        if 'ro' in opts and fstype not in ['iso9660', 'udf']:
            log.debug(f"Skipping read-only partition: {mountpoint}")
            return True
            
        return False

    def _check_drive_for_marker(self, mountpoint: str) -> bool:
        """
        Checks if a drive contains the PondTV marker.
        
        Args:
            mountpoint: Path to check
            
        Returns:
            True if marker is found and drive is accessible
        """
        try:
            # First check if the mountpoint is accessible
            if not os.path.exists(mountpoint) or not os.access(mountpoint, os.R_OK):
                log.debug(f"Drive not accessible: {mountpoint}")
                return False
            
            marker_path = os.path.join(mountpoint, self.marker)
            
            # Check for the marker (case-insensitive on case-insensitive filesystems)
            if os.path.exists(marker_path):
                return True
                
            # Try case-insensitive search for the marker
            try:
                for item in os.listdir(mountpoint):
                    if item.lower() == self.marker.lower():
                        log.info(f"Found marker '{item}' (case-insensitive match)")
                        return True
            except (PermissionError, OSError) as e:
                log.debug(f"Cannot list directory contents of {mountpoint}: {e}")
                return False
                
        except Exception as e:
            log.debug(f"Error checking drive {mountpoint}: {e}")
            return False
            
        return False

    def is_drive_still_connected(self, drive_path: str) -> bool:
        """
        Checks if the specified drive path still exists and is accessible.

        Args:
            drive_path: The path of the drive to check.

        Returns:
            True if the drive is still connected and accessible, False otherwise.
        """
        if not drive_path:
            return False
            
        try:
            # Check if path exists and is accessible
            if not os.path.exists(drive_path):
                log.debug(f"Drive path no longer exists: {drive_path}")
                return False
                
            if not os.access(drive_path, os.R_OK):
                log.debug(f"Drive no longer accessible: {drive_path}")
                return False
            
            # Verify the marker is still there
            if not self._check_drive_for_marker(drive_path):
                log.debug(f"Marker no longer found on drive: {drive_path}")
                return False
                
            return True
            
        except Exception as e:
            log.debug(f"Error checking drive connectivity for {drive_path}: {e}")
            return False

if __name__ == '__main__':
    # Test script for the USBManager
    log.info("--- Running USBManager Test ---")
    
    manager = USBManager()
    media_drive_path = manager.find_media_drive()
    
    if media_drive_path:
        log.info(f"Success! Media drive found: {media_drive_path}")
        
        # Test the is_drive_still_connected method
        is_connected = manager.is_drive_still_connected(media_drive_path)
        log.info(f"Is drive still connected? {is_connected}")
    else:
        log.warning("Test complete, but no media drive was found.")
        log.info("To test properly, connect a USB drive containing a 'Movies' directory.")

    log.info("--- Test Complete ---") 