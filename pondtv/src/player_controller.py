import mpv
import os
import time
from .utils import log

class PlayerController:
    """Handles the mpv player instance and playback controls with robust state management."""

    def __init__(self, media_path_prefix: str = ""):
        """
        Initializes the PlayerController.

        Args:
            media_path_prefix: A path to prepend to the media filepaths from
                               the database. Useful if the script is not running
                               from the media drive root.
        """
        log.info("Initializing PlayerController...")
        self.media_path_prefix = media_path_prefix
        self._is_playing = False
        self._current_file = None
        self._player_crashed = False
        
        # Configure mpv player with error handling
        try:
            self.player = mpv.MPV(
                ytdl=False,
                input_default_bindings=True,
                input_vo_keyboard=True,
                fullscreen=True,
                # Improve stability and error handling
                keep_open='always',  # Don't exit on file end
                idle=True,          # Keep player alive between files
                # Add more mpv options here as needed for a kiosk-like experience
            )
            
            # Set up event handlers for better state tracking
            self.player.observe_property('time-pos', self._time_pos_handler)
            self.player.observe_property('eof-reached', self._eof_handler)
            self.player.observe_property('playback-abort', self._abort_handler)
            
            log.info("PlayerController initialized successfully.")
            
        except Exception as e:
            log.error(f"Failed to initialize MPV player: {e}")
            self.player = None
            self._player_crashed = True

    @property
    def is_playing(self) -> bool:
        """Check if the player is currently active and playing content."""
        if self._player_crashed or not self.player:
            return False
            
        try:
            # Multiple checks for robust state detection
            if not self._is_playing:
                return False
                
            # Check if player is still responsive
            if self.player.playback_abort:
                self._is_playing = False
                return False
                
            # Check if we have a valid time position (more reliable than just checking for None)
            time_pos = self.player.time_pos
            if time_pos is None and self._current_file:
                # Give it a moment for initialization
                time.sleep(0.1)
                time_pos = self.player.time_pos
                
            # If we still don't have time_pos after playing for a bit, something's wrong
            if time_pos is None and self._is_playing:
                # Check if the file actually exists
                if self._current_file and not os.path.exists(self._current_file):
                    log.warning(f"Current file no longer exists: {self._current_file}")
                    self._is_playing = False
                    return False
                    
            return self._is_playing
            
        except Exception as e:
            log.error(f"Error checking playback state: {e}")
            self._player_crashed = True
            self._is_playing = False
            return False

    def _time_pos_handler(self, name, value):
        """Handle time position updates for state tracking."""
        # This can be used later for resume functionality or progress bars
        if value is not None and value > 0:
            self._is_playing = True

    def _eof_handler(self, name, value):
        """Handle end-of-file events."""
        if value:
            log.info("Playback reached end of file.")
            self._is_playing = False

    def _abort_handler(self, name, value):
        """Handle playback abort events."""
        if value:
            log.info("Playback was aborted.")
            self._is_playing = False

    def play(self, media_item: dict, start_pos: int = 0):
        """
        Plays a given media item. This is a non-blocking call.

        Args:
            media_item: A dictionary containing media details, including 'filepath'.
            start_pos: The position in seconds to start playback from.
        """
        if self._player_crashed or not self.player:
            log.error("Cannot play: player is not available or has crashed.")
            return False

        filepath = media_item.get('filepath')
        if not filepath:
            log.error("Media item has no 'filepath' to play.")
            return False

        full_path = os.path.join(self.media_path_prefix, filepath)
        
        if not os.path.exists(full_path):
            log.error(f"Media file does not exist: {full_path}")
            return False

        log.info(f"Playing media: {full_path}")
        try:
            self._current_file = full_path
            self._is_playing = True
            
            self.player.play(full_path)
            
            if start_pos > 0:
                # Give the player a moment to load before seeking
                time.sleep(0.5)
                self.player.seek(start_pos, 'absolute')
                log.info(f"Seeking to position: {start_pos}s")
                
            return True
            
        except Exception as e:
            log.error(f"Error playing {full_path}: {e}")
            self._is_playing = False
            self._current_file = None
            return False

    def stop_playback(self):
        """Stops the current playback."""
        if not self.player or self._player_crashed:
            return
            
        log.info("Stopping current playback.")
        try:
            self.player.command('stop')
            self._is_playing = False
            self._current_file = None
        except Exception as e:
            log.error(f"Error stopping playback: {e}")

    def toggle_pause(self):
        """Toggles the pause state of the player."""
        if not self.is_playing or self._player_crashed or not self.player:
            log.warning("Cannot toggle pause: not currently playing or player crashed.")
            return
            
        try:
            current_pause_state = self.player.pause
            self.player.pause = not current_pause_state
            log.info(f"Playback {'paused' if self.player.pause else 'resumed'}.")
        except Exception as e:
            log.error(f"Error toggling pause: {e}")

    def restart_playback(self):
        """Restarts the current video from the beginning."""
        if not self.is_playing or self._player_crashed or not self.player:
            log.warning("Cannot restart: not currently playing or player crashed.")
            return
            
        try:
            self.player.seek(0, 'absolute')
            log.info("Restarted playback.")
        except Exception as e:
            log.error(f"Error restarting playback: {e}")

    def set_volume(self, level: int):
        """Sets the player volume."""
        if not self.player or self._player_crashed:
            return
            
        try:
            safe_level = max(0, min(100, level))
            self.player.volume = safe_level
            log.info(f"Volume set to {safe_level}")
        except Exception as e:
            log.error(f"Error setting volume: {e}")

    def change_volume(self, amount: int):
        """Changes the volume by a given amount."""
        if not self.player or self._player_crashed:
            return
            
        try:
            current_volume = self.player.volume
            if not isinstance(current_volume, (int, float)):
                current_volume = 70
            new_level = int(current_volume + amount)
            self.set_volume(new_level)
        except Exception as e:
            log.error(f"Error changing volume: {e}")

    def get_playback_state(self) -> dict:
        """Returns the current playback state."""
        if not self.player or self._player_crashed or not self.is_playing:
            return {'position': 0, 'duration': 0, 'paused': True}
        
        try:
            return {
                'position': self.player.time_pos or 0,
                'duration': self.player.duration or 0,
                'paused': self.player.pause or False
            }
        except Exception as e:
            log.error(f"Error getting playback state: {e}")
            return {'position': 0, 'duration': 0, 'paused': True}

    def shutdown(self):
        """Stops playback and terminates the mpv instance."""
        log.info("Shutting down PlayerController.")
        
        if self.player and not self._player_crashed:
            try:
                self.stop_playback()
                self.player.terminate()
            except Exception as e:
                log.error(f"Error during player shutdown: {e}")
            finally:
                self.player = None
                
        self._is_playing = False
        self._current_file = None
        self._player_crashed = False

if __name__ == '__main__':
    import time

    log.info("--- Running PlayerController Test ---")
    # This test requires a dummy file to play.
    # Note: This will open a fullscreen mpv window.
    
    dummy_dir = 'temp_player_test'
    dummy_file_name = 'test_video.txt'
    dummy_file_path = os.path.join(dummy_dir, dummy_file_name)
    
    os.makedirs(dummy_dir, exist_ok=True)
    with open(dummy_file_path, 'w') as f:
        f.write("This is a test file, not a real video.")

    log.info("Step 1: Initializing player...")
    # We pass the directory as the prefix
    player_controller = PlayerController(media_path_prefix=dummy_dir)
    
    # The media_item only needs the filename, not the full path
    test_media_item = {'filepath': dummy_file_name}

    log.info("Step 2: Starting playback (will stop automatically in 5s)...")
    
    # Since player.wait_for_playback() is blocking, we can't easily
    # time it out here. For a real test, you'd run this in a thread.
    # For this demonstration, we'll just show it can be called.
    # The user should see an mpv window open and then close it manually.
    print("\n\nMANUAL TEST REQUIRED: An mpv window will open playing a text file.")
    print("Please close the mpv window manually to continue the test.\n\n")

    player_controller.play(test_media_item)
    
    # Since play is non-blocking now, we wait a bit before stopping
    time.sleep(5)
    player_controller.toggle_pause()
    time.sleep(2)
    player_controller.shutdown()

    log.info("Playback finished or was stopped by the user.")
    
    # Cleanup
    os.remove(dummy_file_path)
    os.rmdir(dummy_dir)
    log.info("--- Test Complete ---") 