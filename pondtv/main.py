#!/usr/bin/env python3
"""
PondTV Main Application
A zen-inspired offline media experience that boots directly into playback.
"""

import os
import sys
import time
import signal
import queue
import threading
from enum import Enum
from utils import log
from usb_manager import USBManager
from database_manager import DatabaseManager
from media_scanner import MediaScanner
from playlist_engine import PlaylistEngine
from player_controller import PlayerController

class AppState(Enum):
    """Application state enumeration for better state management."""
    STARTING = "starting"
    WAITING_FOR_MEDIA = "waiting_for_media"
    INITIALIZING = "initializing"
    PLAYING = "playing"
    SHUTTING_DOWN = "shutting_down"

class PondTVApp:
    """Main PondTV application orchestrator with proper component lifecycle management."""
    
    def __init__(self):
        """Initialize the PondTV application."""
        self.state = AppState.STARTING
        self.state_lock = threading.Lock()
        
        # Core managers - initialized once
        self.usb_manager = USBManager()
        
        # Media-dependent components - recreated per drive
        self.media_path = None
        self.db_manager = None
        self.player_controller = None
        self.playlist_engine = None
        
        # Playback state
        self.current_playlist = []
        self.current_index = 0
        self.running = True
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.log = log
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        log.info(f"Received signal {signum}, shutting down gracefully...")
        self._set_state(AppState.SHUTTING_DOWN)
        self.running = False
        self._cleanup_all_components()
        sys.exit(0)
    
    def _set_state(self, new_state: AppState):
        """Thread-safe state management."""
        with self.state_lock:
            if self.state != new_state:
                log.info(f"State transition: {self.state.value} -> {new_state.value}")
                self.state = new_state
    
    def _cleanup_media_components(self):
        """Clean up media-dependent components safely."""
        log.info("Cleaning up media-dependent components...")
        
        if self.player_controller:
            try:
                self.player_controller.shutdown()
            except Exception as e:
                log.error(f"Error shutting down player: {e}")
            finally:
                self.player_controller = None
        
        self.playlist_engine = None
        self.db_manager = None
        self.media_path = None
        
        log.info("Media components cleaned up.")
    
    def _cleanup_all_components(self):
        """Clean up all components during shutdown."""
        self._cleanup_media_components()

    def wait_for_media_drive(self) -> bool:
        """Wait for a valid media drive to be connected. Returns True if found, False if shutting down."""
        self._set_state(AppState.WAITING_FOR_MEDIA)
        log.info("PondTV waiting for media drive...")
        
        while self.running:
            self.media_path = self.usb_manager.find_media_drive()
            if self.media_path:
                log.info(f"Media drive found at: {self.media_path}")
                return True
            
            log.info("No media drive found. Waiting 5 seconds before retry...")
            time.sleep(5)
        
        return False

    def initialize_media_components(self) -> bool:
        """Initialize all media-dependent components. Returns True on success."""
        if not self.media_path:
            log.error("Cannot initialize media components without media path")
            return False
            
        self._set_state(AppState.INITIALIZING)
        log.info("Initializing media components...")
        
        try:
            # Initialize database manager
            db_path = os.path.join(self.media_path, 'media_library.yml')
            self.db_manager = DatabaseManager(db_path)
            
            # Initialize and scan media database
            db_content = self.db_manager.load()
            if not db_content or (not db_content.get('movies') and not db_content.get('series')):
                log.info("Database is empty or missing. Running media scan...")
                scanner = MediaScanner(self.media_path, self.db_manager)
                scanner.scan()
                db_content = self.db_manager.load()
            
            # Create playlist
            self.playlist_engine = PlaylistEngine(db_content)
            self.current_playlist = self.playlist_engine.create_playlist()
            
            if not self.current_playlist:
                log.warning("No unseen content available. All media has been watched!")
                return False
            
            # Initialize player controller
            self.player_controller = PlayerController(media_path_prefix=self.media_path)
            
            log.info(f"Media components initialized successfully. Playlist has {len(self.current_playlist)} items.")
            return True
            
        except Exception as e:
            log.error(f"Failed to initialize media components: {e}", exc_info=True)
            self._cleanup_media_components()
            return False

    def start_playback(self):
        """Start the main playback loop."""
        self._set_state(AppState.PLAYING)
        
        while self.running and 0 <= self.current_index < len(self.current_playlist):
            # Check for USB disconnect before starting next item
            if not self.media_path or not self.usb_manager.is_drive_still_connected(self.media_path):
                log.warning("Media drive disconnected. Returning to scan mode.")
                break

            current_item = self.current_playlist[self.current_index]
            start_pos = current_item.get('resume_position') or 0
            
            self.player_controller.play(current_item, start_pos=start_pos)
            
            # Wait for playback to finish
            while self.player_controller and self.player_controller.is_playing:
                time.sleep(1)
                
            # Mark as seen and move to next
            self.update_media_status(current_item)
            self.current_index += 1
        
        log.info("Playlist finished or app is shutting down.")

    def update_media_status(self, media_item: dict):
        """Update media status in database."""
        try:
            if self.db_manager:
                # Mark as seen
                media_item['status'] = 'Seen'
                media_item['resume_position'] = 0
                self.db_manager.save()
        except Exception as e:
            log.error(f"Error updating media status: {e}")

    def run(self):
        """Main application loop with proper state management."""
        log.info("🌊 PondTV starting...")
        
        try:
            while self.running:
                # Step 1: Wait for media drive
                if not self.wait_for_media_drive():
                    break
                
                # Step 2: Initialize components
                if not self.initialize_media_components():
                    log.warning("Failed to initialize. Waiting for drive reconnection...")
                    self._cleanup_media_components()
                    time.sleep(5)
                    continue
                
                # Step 3: Start playback
                self.start_playback()
                
                # Clean up after playback ends
                self._cleanup_media_components()
                
        except Exception as e:
            log.error(f"Unexpected error in main loop: {e}", exc_info=True)
        finally:
            self._cleanup_all_components()
            log.info("🌊 PondTV stopped.")

def main():
    """Entry point for PondTV application."""
    app = PondTVApp()
    app.run()
    return 0

if __name__ == '__main__':
    sys.exit(main())
