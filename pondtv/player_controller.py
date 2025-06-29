import mpv
import os
from .utils import log
import threading

class PlayerController:
    """Handles the mpv player instance and playback controls."""

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
        # Configure mpv player
        self.player = mpv.MPV(
            ytdl=False,
            input_default_bindings=True,
            input_vo_keyboard=True,
            fullscreen=True,
            # Add more mpv options here as needed for a kiosk-like experience
            # e.g., --no-border, --no-window-title
        )
        self._is_playing = False
        self.player.observe_property('playback-time', self._time_pos_handler)
        self.player.register_event_callback('end-file', self._end_file_handler)
        log.info("PlayerController initialized.")

    @property
    def is_playing(self):
        """Returns True if the player is currently active."""
        return self._is_playing

    def _time_pos_handler(self, name, value):
        """Handles time position updates for resume functionality."""
        # This can be used later if needed
        pass

    def _end_file_handler(self, event):
        """Callback for when a file finishes playing."""
        log.info("File playback finished (end-file event).")
        self._is_playing = False

    def play(self, media_item: dict, start_pos: int = 0):
        """
        Plays a given media item.

        Args:
            media_item: A dictionary containing media details, including 'filepath'.
            start_pos: The time in seconds to start playback from.
        """
        filepath = media_item.get('filepath')
        if not filepath:
            log.error("Media item has no 'filepath' to play.")
            return

        full_path = os.path.join(self.media_path_prefix, filepath)
        log.info(f"Playing media: {full_path} from {start_pos}s")

        try:
            self._is_playing = True
            self.player.play(full_path, start=start_pos)
            self.player.wait_for_playback()
            # Playback has finished naturally or was stopped.
            # The _end_file_handler will set _is_playing to False.
            log.info(f"Finished playing: {filepath}")
        except Exception as e:
            log.error(f"Error playing {full_path}: {e}")
            self._is_playing = False

    def shutdown(self):
        """Stops playback and terminates the player."""
        log.info("Shutting down player.")
        self._is_playing = False
        self.player.terminate()

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

    log.info("Step 2: Starting playback in a separate thread...")
    # Playback is blocking, so we run it in a thread for the test
    playback_thread = threading.Thread(target=player_controller.play, args=(test_media_item,))
    playback_thread.start()

    time.sleep(1) # Give it a moment to start
    assert player_controller.is_playing, "Player should be playing"
    log.info("Player is playing as expected.")

    log.info("Step 3: Shutting down player after 3 seconds...")
    time.sleep(3)
    player_controller.shutdown()
    time.sleep(1) # Give it a moment to shut down
    assert not player_controller.is_playing, "Player should not be playing"
    log.info("Player shut down correctly.")
    
    playback_thread.join()

    # Cleanup
    os.remove(dummy_file_path)
    os.rmdir(dummy_dir)
    log.info("--- Test Complete ---") 