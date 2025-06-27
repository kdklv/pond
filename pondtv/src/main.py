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
from .utils import log
from .usb_manager import USBManager
from .database_manager import DatabaseManager
from .media_scanner import MediaScanner
from .playlist_engine import PlaylistEngine
from .player_controller import PlayerController
from .input_handler import InputHandler
from .config_manager import ConfigManager
from .ui_manager import UIManager

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
        self.input_handler = None
        self.input_queue = queue.Queue()
        
        # Media-dependent components - recreated per drive
        self.media_path = None
        self.db_manager = None
        self.config_manager = None
        self.player_controller = None
        self.ui_manager = None
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
        
        if self.ui_manager:
            self.ui_manager = None
            
        if self.player_controller:
            try:
                self.player_controller.shutdown()
            except Exception as e:
                log.error(f"Error shutting down player: {e}")
            finally:
                self.player_controller = None
        
        self.playlist_engine = None
        self.config_manager = None
        self.db_manager = None
        self.media_path = None
        
        log.info("Media components cleaned up.")
    
    def _cleanup_all_components(self):
        """Clean up all components during shutdown."""
        self._cleanup_media_components()
        
        if self.input_handler and self.input_handler.is_alive():
            try:
                self.input_handler.stop()
                self.input_handler.join(timeout=2.0)
            except Exception as e:
                log.error(f"Error stopping input handler: {e}")
            finally:
                self.input_handler = None

    def _initialize_input_handler(self):
        """Initialize input handler if not already running."""
        if not self.input_handler or not self.input_handler.is_alive():
            log.info("Starting input handler...")
            self.input_handler = InputHandler(self.input_queue)
            self.input_handler.start()

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
            
            # Initialize config manager  
            self.config_manager = ConfigManager(self.media_path)
            
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
            
            # Initialize UI manager
            self.ui_manager = UIManager(self.player_controller, self.config_manager, self.current_playlist)
            
            log.info(f"Media components initialized successfully. Playlist has {len(self.current_playlist)} items.")
            return True
            
        except Exception as e:
            log.error(f"Failed to initialize media components: {e}", exc_info=True)
            self._cleanup_media_components()
            return False

    def start_playback(self, media_path):
        """Initialize player and start the main interactive playback loop."""
        self.player_controller = PlayerController(media_path_prefix=media_path)
        
        while self.running and 0 <= self.current_index < len(self.current_playlist):
            if not self.ui_manager:
                self.log.error("UIManager not initialized, cannot proceed.")
                break
            # Check for USB disconnect before starting next item
            if not self.media_path or not self.usb_manager.is_drive_still_connected(self.media_path):
                log.warning("Media drive disconnected. Returning to scan mode.")
                # We break the loop and `run` method will cycle back to wait_for_media_drive
                break

            current_item = self.current_playlist[self.current_index]
            start_pos = current_item.get('resume_position') or 0
            
            self.ui_manager.show_title_overlay(current_item)
            self.player_controller.play(current_item, start_pos=start_pos)
            
            # This is the inner, non-blocking loop for a single video
            playback_interrupted = self.handle_playback_loop()
            
            self.update_media_status(current_item, playback_interrupted)
            
            if not playback_interrupted:
                # Move to next item only if playback finished naturally
                self.current_index += 1
        
        log.info("Playlist finished or app is shutting down.")

    def handle_playback_loop(self) -> bool:
        """
        Manages the state while a video is playing, checking for input.
        Returns True if playback was interrupted by user, False otherwise.
        """
        while self.player_controller and self.player_controller.is_playing:
            try:
                action = self.input_queue.get(timeout=0.1)
                interrupted = self.handle_action(action)
                if interrupted:
                    return True # User action caused playback to stop
            except queue.Empty:
                continue # No input, just loop
        return False

    def handle_action(self, action: str) -> bool:
        """
        Processes a single action from the input queue.
        Returns True if the action should interrupt playback.
        """
        if not self.player_controller or not self.ui_manager or not self.config_manager:
            self.log.error("Cannot handle action, components not initialized.")
            return False

        # If guide is visible, route controls there
        if self.ui_manager.is_guide_visible:
            return self._handle_guide_action(action)

        # Global playback controls
        return self._handle_playback_action(action)

    def _handle_guide_action(self, action: str) -> bool:
        """Handles input when the channel guide is visible."""
        if not self.ui_manager or not self.player_controller:
            return False

        if action in ['up', 'down', 'next', 'previous', 'select', 'show_guide']:
            selected_item = self.ui_manager.guide_navigate(action)
            if selected_item:
                self.player_controller.stop_playback()
                try:
                    self.current_index = self.current_playlist.index(selected_item)
                    return True # Interrupt playback to jump to new item
                except ValueError:
                    self.log.warning("Selected item not found in playlist.")
        elif action == 'shutdown':
            self.running = False
            return True
        
        return False # Absorb other actions

    def _handle_playback_action(self, action: str) -> bool:
        """Handles input during normal playback."""
        if not self.player_controller or not self.config_manager or not self.ui_manager:
            return False

        if action == 'toggle_pause':
            self.player_controller.toggle_pause()
        elif action == 'restart':
            self.player_controller.restart_playback()
        elif action == 'volume_up':
            step_val = self.config_manager.get('player.volume_step', 5)
            step = int(step_val) if isinstance(step_val, (int, float, str)) else 5
            self.player_controller.change_volume(step)
        elif action == 'volume_down':
            step_val = self.config_manager.get('player.volume_step', 5)
            step = int(step_val) if isinstance(step_val, (int, float, str)) else 5
            self.player_controller.change_volume(-step)
        elif action == 'toggle_mute':
            default_vol_val = self.config_manager.get('player.volume_default', 70)
            default_vol = int(default_vol_val) if isinstance(default_vol_val, (int, float, str)) else 70
            vol = self.player_controller.player.volume if self.player_controller.player else None
            current_vol = vol if isinstance(vol, (int, float)) else default_vol
            self.player_controller.set_volume(0 if current_vol > 0 else default_vol)
        elif action == 'next':
            self.player_controller.stop_playback()
            self.current_index += 1
            return True
        elif action == 'previous':
            self.player_controller.stop_playback()
            self.current_index = max(0, self.current_index - 1)
            return True
        elif action == 'mark_seen':
            self.update_media_status(self.current_playlist[self.current_index], interrupted=True, force_seen=True)
        elif action == 'show_guide':
            self.ui_manager.toggle_guide()
        elif action == 'shutdown':
            self.running = False
            self.player_controller.stop_playback()
            return True
            
        return False

    def update_media_status(self, media_item: dict, interrupted: bool, force_seen: bool = False):
        """Mark a media item as seen or save resume position in the database."""
        if not self.db_manager or not self.player_controller:
            log.error("Cannot save state, component not initialized.")
            return

        state = self.player_controller.get_playback_state()
        position = state.get('position', 0)
        duration = state.get('duration', 0)

        # Determine new status and resume position
        new_status = media_item.get('status', 'Unseen')
        new_resume_pos = None

        # Mark as 'Seen' if forced, or if it played to 95% completion
        is_finished = (duration > 0 and position / duration >= 0.95)
        if force_seen or is_finished:
            new_status = 'Seen'
            new_resume_pos = None  # Clear resume position when marking as seen
            log.info(f"Marking '{media_item.get('title', media_item['filepath'])}' as SEEN.")
        elif interrupted and position > 0:
            new_resume_pos = int(position)
            log.info(f"Saving resume position for '{media_item.get('title', media_item['filepath'])}' at {new_resume_pos}s.")

        # Use thread-safe database update method
        filepath = media_item['filepath']
        success = self.db_manager.update_item_status(filepath, new_status, new_resume_pos)
        
        if not success:
            log.error(f"Failed to update status for '{filepath}' in database.")
    
    def run(self):
        """Main application loop."""
        # Start the input handler thread
        self._initialize_input_handler()
        
        while self.running:
            try:
                # Wait for media drive
                found = self.wait_for_media_drive()
                if not found or not self.running:
                    break
                
                # Initialize media components
                if not self.initialize_media_components():
                    log.info("No content to play. Waiting for new media or shutdown.")
                    # Wait for a while before re-checking, or until shutdown is triggered
                    time.sleep(10)
                    continue
                
                # Start playback loop
                self.start_playback(self.media_path)
                
            except Exception as e:
                log.error(f"Fatal error in PondTV main loop: {e}", exc_info=True)
                # Wait a bit before retrying to prevent rapid-fire crash loops
                time.sleep(5)
            finally:
                self._cleanup_media_components()
                log.info("Playback loop finished. Restarting wait for media drive...")
        
        # Cleanup
        self._cleanup_all_components()
        log.info("PondTV has shut down.")


def main():
    """Entry point for PondTV application."""
    app = PondTVApp()
    app.run()

if __name__ == '__main__':
    main() 