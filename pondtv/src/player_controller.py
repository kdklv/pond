import mpv
import os
from .utils import log

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
        self.player.observe_property('time-pos', self.time_pos_handler)
        log.info("PlayerController initialized.")

    def time_pos_handler(self, name, value):
        """A placeholder for handling time position updates."""
        # This can be used later for resume functionality or progress bars
        pass

    def play(self, media_item: dict):
        """
        Plays a given media item.

        Args:
            media_item: A dictionary containing media details, including 'filepath'.
        """
        filepath = media_item.get('filepath')
        if not filepath:
            log.error("Media item has no 'filepath' to play.")
            return

        full_path = os.path.join(self.media_path_prefix, filepath)
        log.info(f"Playing media: {full_path}")

        try:
            self.player.play(full_path)
            # The wait_for_playback() will block until the video finishes
            # or is stopped by the user.
            self.player.wait_for_playback()
            log.info(f"Finished playing: {filepath}")
        except Exception as e:
            log.error(f"Error playing {full_path}: {e}")

    def stop(self):
        """Stops playback."""
        log.info("Stopping playback.")
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

    log.info("Step 2: Starting playback (will stop automatically in 5s)...")
    
    # Since player.wait_for_playback() is blocking, we can't easily
    # time it out here. For a real test, you'd run this in a thread.
    # For this demonstration, we'll just show it can be called.
    # The user should see an mpv window open and then close it manually.
    print("\n\nMANUAL TEST REQUIRED: An mpv window will open playing a text file.")
    print("Please close the mpv window manually to continue the test.\n\n")

    player_controller.play(test_media_item)

    log.info("Playback finished or was stopped by the user.")
    
    # Cleanup
    player_controller.stop()
    os.remove(dummy_file_path)
    os.rmdir(dummy_dir)
    log.info("--- Test Complete ---") 