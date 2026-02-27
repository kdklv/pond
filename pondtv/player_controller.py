import os
import mpv
from pondtv.utils import log


class PlayerController:
    """Wraps an mpv player instance and provides simple blocking playback."""

    def __init__(self, media_path_prefix: str = ""):
        """
        Args:
            media_path_prefix: Prepended to every filepath from the database.
                               Typically the USB drive mount point.
        """
        log.info("Initializing PlayerController...")
        self.media_path_prefix = media_path_prefix
        self.player = mpv.MPV(
            ytdl=False,
            input_default_bindings=True,
            input_vo_keyboard=True,
            fullscreen=True,
        )
        log.info("PlayerController initialized.")

    def play(self, media_item: dict, start_pos: float = 0):
        """
        Plays *media_item* and blocks until playback finishes.

        Args:
            media_item:  Dict with at least a 'filepath' key (relative to the
                         media_path_prefix).
            start_pos:   Position in seconds to start from (for resume support).
        """
        filepath = media_item.get('filepath')
        if not filepath:
            log.error("Media item has no 'filepath'; skipping.")
            return

        full_path = os.path.join(self.media_path_prefix, filepath)
        if not os.path.isfile(full_path):
            log.error(f"File not found: {full_path}")
            return

        log.info(f"Playing: {full_path}" + (f" from {start_pos}s" if start_pos else ""))
        try:
            # Set the start position via the mpv property *before* calling play().
            # The value must be a string (seconds or HH:MM:SS).
            if start_pos:
                self.player.start = str(int(start_pos))

            self.player.play(full_path)
            # Block until the file finishes or the player is terminated.
            self.player.wait_for_playback()
            log.info(f"Finished playing: {filepath}")
        except Exception as e:
            log.error(f"Error during playback of {full_path}: {e}")
        finally:
            # Reset start so the next file begins from 0 unless told otherwise.
            self.player.start = None

    def shutdown(self):
        """Stops any active playback and terminates the player process."""
        log.info("Shutting down PlayerController.")
        try:
            self.player.terminate()
        except Exception as e:
            log.error(f"Error terminating player: {e}")
