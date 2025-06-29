import mpv
import os
from .utils import log

class PlayerController:
    """
    Controls the MPV player instance, including playback, volume, and event handling.
    """
    def __init__(self, media_path_prefix: str = ""):
        """
        Initializes the PlayerController.

        Args:
            media_path_prefix: A path to prepend to the media filepaths from
                               the database. Useful if the script is not running
                               from the media drive root.
        """
        log.info("Initializing PlayerController...")
        try:
            self.player = mpv.MPV(
                'osc=no',
                'input-default-bindings=yes',
                'input-vo-keyboard=yes',
                'fullscreen=yes',
                'keep-open=yes',
                'idle=yes',
                'ytdl=no',
                log_handler=log.info
            )
        except Exception as e:
            log.error(f"Failed to initialize MPV player: {e}")
            raise

        self.media_path_prefix = media_path_prefix
        self.current_item = None
        self.on_end_file_callback = None
        self.on_player_quit_callback = None

        self.player.register_event_callback(self._event_handler)
        self.player.observe_property('playback-time', self._time_pos_handler)
        log.info("PlayerController initialized.")

    @property
    def is_playing(self):
        """Returns True if the player is currently active."""
        return self.current_item is not None

    def _time_pos_handler(self, name, value):
        """Handles time position updates for resume functionality."""
        if self.current_item and value:
            self.current_item['resume_position'] = value

    def _event_handler(self, event):
        """
        Generic event handler to dispatch MPV events.
        It's called from a separate thread by the mpv core, so be careful.
        """
        event_name = event.get('event')
        if not event_name:
            return

        if event_name == 'end-file':
            self._end_file_handler(event)
        elif event_name == 'shutdown':
            self._shutdown_handler()

    def _shutdown_handler(self):
        """
        Handles the player shutdown event.
        """
        log.info("Player has shut down.")
        if self.on_player_quit_callback:
            self.on_player_quit_callback()

    def _end_file_handler(self, event):
        """
        Handles the end-of-file event from MPV.
        """
        reason = event.get('reason')
        log.info(f"End of file event, reason: {reason}")
        if self.on_end_file_callback and reason == 'eof':
            if self.current_item:
                self.current_item['status'] = 'Seen'
                self.current_item['resume_position'] = 0
            self.on_end_file_callback()

    def play(self, media_item: dict, start_pos: int = 0):
        """
        Plays a media file.
        """
        if not media_item or 'file_path' not in media_item:
            log.error("Invalid media item provided to play.")
            return

        full_path = os.path.join(self.media_path_prefix, media_item['file_path'])
        log.info(f"Playing '{full_path}' at start_pos {start_pos}")

        try:
            self.current_item = media_item
            self.player.play(full_path, start=start_pos)
        except Exception as e:
            log.error(f"Error playing {full_path}: {e}")
            self.current_item = None

    def register_on_end_file(self, callback):
        self.on_end_file_callback = callback

    def register_on_quit(self, callback):
        self.on_player_quit_callback = callback

    def shutdown(self):
        """Stops playback and terminates the player."""
        log.info("Shutting down player.")
        self.current_item = None
        if hasattr(self, 'player') and self.player:
            self.player.terminate()

    def toggle_pause(self):
        """Toggles pause/resume state."""
        log.info("Toggling pause.")
        self.player.cycle('pause')

    def seek_forward(self):
        log.info("Seeking forward.")
        self.player.seek(10, 'relative')

    def seek_backward(self):
        log.info("Seeking backward.")
        self.player.seek(-10, 'relative')

    def volume_up(self):
        log.info("Volume up.")
        self.player.volume_up()

    def volume_down(self):
        log.info("Volume down.")
        self.player.volume_down()

    def restart_video(self):
        log.info("Restarting video.")
        self.player.seek(0, 'absolute')

    def toggle_mute(self):
        log.info("Toggling mute.")
        self.player.cycle('mute')

    def get_current_item(self):
        return self.current_item

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