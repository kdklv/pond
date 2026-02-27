#!/usr/bin/env python3
"""
PondTV Main Application
A zen-inspired offline media experience that boots directly into playback.
"""

import os
import sys
import time
import signal
import threading
from enum import Enum

from pondtv.utils import log
from pondtv.usb_manager import USBManager
from pondtv.database_manager import DatabaseManager
from pondtv.media_scanner import MediaScanner
from pondtv.playlist_engine import PlaylistEngine
from pondtv.player_controller import PlayerController


class AppState(Enum):
    STARTING = "starting"
    WAITING_FOR_MEDIA = "waiting_for_media"
    INITIALIZING = "initializing"
    PLAYING = "playing"
    SHUTTING_DOWN = "shutting_down"


class PondTVApp:
    """Main PondTV application orchestrator."""

    def __init__(self):
        self.state = AppState.STARTING
        self._state_lock = threading.Lock()
        self.running = True

        self.usb_manager = USBManager()

        # These are set per-drive and reset when the drive is removed.
        self.media_path: str | None = None
        self.db_manager: DatabaseManager | None = None
        self.db_content: dict | None = None
        self.player: PlayerController | None = None
        self.playlist: list[dict] = []
        self.playlist_index: int = 0

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _set_state(self, new_state: AppState):
        with self._state_lock:
            if self.state != new_state:
                log.info(f"State: {self.state.value} -> {new_state.value}")
                self.state = new_state

    def _signal_handler(self, signum, frame):
        log.info(f"Signal {signum} received — shutting down.")
        self.running = False
        self._set_state(AppState.SHUTTING_DOWN)
        self._teardown()
        sys.exit(0)

    # ------------------------------------------------------------------
    # Setup / teardown
    # ------------------------------------------------------------------

    def _setup_media(self) -> bool:
        """
        Initialise all media-dependent components for the current drive.
        Returns True on success.
        """
        self._set_state(AppState.INITIALIZING)
        try:
            db_path = os.path.join(self.media_path, 'media_library.yml')
            self.db_manager = DatabaseManager(db_path)
            self.db_content = self.db_manager.load_and_validate(self.media_path)

            engine = PlaylistEngine(self.db_content)
            self.playlist = engine.create_playlist()
            self.playlist_index = 0

            if not self.playlist:
                log.warning("No unseen content — everything has been watched.")
                return False

            self.player = PlayerController(media_path_prefix=self.media_path)
            log.info(f"Ready. Playlist has {len(self.playlist)} items.")
            return True

        except Exception as e:
            log.error(f"Failed to set up media components: {e}", exc_info=True)
            self._teardown_media()
            return False

    def _teardown_media(self):
        """Release media-dependent components."""
        if self.player:
            try:
                self.player.shutdown()
            except Exception as e:
                log.error(f"Error shutting down player: {e}")
            finally:
                self.player = None

        self.db_manager = None
        self.db_content = None
        self.playlist = []
        self.playlist_index = 0
        self.media_path = None

    def _teardown(self):
        """Full teardown — media components + USB."""
        self._teardown_media()
        self.usb_manager.unmount_drive()

    # ------------------------------------------------------------------
    # Main loop phases
    # ------------------------------------------------------------------

    def _wait_for_drive(self) -> bool:
        """Block until a media drive is found. Returns False if shutting down."""
        self._set_state(AppState.WAITING_FOR_MEDIA)
        log.info("Waiting for media drive...")
        while self.running:
            path = self.usb_manager.find_media_drive()
            if path:
                self.media_path = path
                log.info(f"Media drive found: {path}")
                return True
            time.sleep(5)
        return False

    def _play_all(self):
        """Play through the playlist, marking each item seen as we go."""
        self._set_state(AppState.PLAYING)

        while self.running and self.playlist_index < len(self.playlist):
            if not self.usb_manager.is_drive_still_connected(self.media_path):
                log.warning("Drive disconnected — stopping playback.")
                break

            item = self.playlist[self.playlist_index]

            # play() blocks until the file finishes or the player crashes.
            self.player.play(item, start_pos=item.get('resume_position', 0))

            self._mark_seen(item)
            self.playlist_index += 1

        log.info("Playlist finished.")

    def _mark_seen(self, item: dict):
        """Persist 'Seen' status for the just-played item."""
        try:
            item['status'] = 'Seen'
            item['resume_position'] = 0
            self.db_manager.save(self.db_content)
        except Exception as e:
            log.error(f"Failed to save watch status: {e}")

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def run(self):
        log.info("PondTV starting...")
        try:
            while self.running:
                if not self._wait_for_drive():
                    break

                if not self._setup_media():
                    log.warning("Could not initialise media. Retrying in 10s...")
                    self._teardown_media()
                    time.sleep(10)
                    continue

                self._play_all()
                self._teardown_media()

        except Exception as e:
            log.error(f"Unexpected error: {e}", exc_info=True)
        finally:
            self._teardown()
            log.info("PondTV stopped.")


def main():
    PondTVApp().run()
    return 0


if __name__ == '__main__':
    sys.exit(main())
