import os
import psutil
from pondtv.utils import log

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
        log.info(f"USBManager initialized, looking for marker: '{self.marker}'")

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
            # On Linux, USB drives are often in /media. On macOS, /Volumes.
            # This check helps to ignore system partitions.
            is_media_drive = 'removable' in p.opts or p.mountpoint.startswith(('/media', '/Volumes'))
            
            if not is_media_drive:
                continue

            log.info(f"Checking potential drive at {p.mountpoint}...")
            marker_path = os.path.join(p.mountpoint, self.marker)
            if os.path.exists(marker_path):
                log.info(f"PondTV media drive found at: {p.mountpoint}")
                return p.mountpoint
                
        log.warning("No PondTV media drive found.")
        return None

    def is_drive_still_connected(self, path: str) -> bool:
        """
        Checks if a given path is still a valid and connected mountpoint.
        
        Args:
            path: The mountpoint path to check.
            
        Returns:
            True if the drive is still connected, False otherwise.
        """
        if not path or not os.path.exists(path):
            return False
            
        # A simple way to check is to see if it's still in the list of mounts.
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
        log.info("To test properly, connect a USB drive containing a 'Movies' directory.")
        
    log.info("--- Test Complete ---") 