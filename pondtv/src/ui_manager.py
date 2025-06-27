from .utils import log

# Forward reference for type hinting if mpv is not installed
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    try:
        import mpv
    except ImportError:
        mpv = None

from .player_controller import PlayerController
from .config_manager import ConfigManager

class UIManager:
    """Manages all on-screen display (OSD) elements."""

    def __init__(self, player_controller: PlayerController, config: ConfigManager, playlist: list):
        """
        Initializes the UIManager.

        Args:
            player_controller: The application's PlayerController instance.
            config: The application's ConfigManager instance.
            playlist: The current playlist of media items.
        """
        if not hasattr(player_controller, 'player') or not player_controller.player:
            raise ValueError("PlayerController is not properly initialized.")
        
        self.player = player_controller.player
        self.config = config
        self.playlist = playlist
        self.log = log
        
        self.is_guide_visible = False
        self.guide_selection_index = 0
        self.guide_page = 0
        self.guide_page_size = int(self.config.get('ui.guide_page_size', 10))

    def show_title_overlay(self, media_item: dict):
        """Displays the title of the currently playing media item."""
        if 'series_name' in media_item:
            title = f"{media_item['series_name']} - S{media_item['season']:02d}E{media_item['episode']:02d}"
        else:
            title = f"{media_item.get('title', 'Unknown Title')} ({media_item.get('year', 'N/A')})"
        
        duration = int(self.config.get('ui.title_overlay_duration', 5))
        self.log.info(f"Showing title overlay: '{title}' for {duration}s")
        
        # OSD Level 3 is typically high enough to show over subtitles.
        # The text format allows for font size, alignment, etc.
        # {\an7} is top-left alignment.
        formatted_text = f"{{\\an7}}{{\\fs_PROPERTY_ADD=20}}{title}"
        self.player.osd_show_text(formatted_text, duration=duration * 1000, level=3)

    def toggle_guide(self):
        """Toggles the visibility of the channel guide."""
        self.is_guide_visible = not self.is_guide_visible
        if self.is_guide_visible:
            self.log.info("Channel guide enabled.")
            self._render_guide()
        else:
            self.log.info("Channel guide disabled.")
            self.player.osd_show_text("", duration=0, level=3) # Clear the OSD

    def guide_navigate(self, direction: str) -> dict | None:
        """
        Handles navigation within the channel guide.

        Args:
            direction: 'up', 'down', 'select'.

        Returns:
            The selected media_item if 'select' is chosen, otherwise None.
        """
        if not self.is_guide_visible:
            return None

        if direction == 'up':
            self.guide_selection_index = max(0, self.guide_selection_index - 1)
        elif direction == 'down':
            self.guide_selection_index = min(len(self.playlist) - 1, self.guide_selection_index + 1)
        elif direction == 'select':
            self.toggle_guide() # Hide guide on selection
            return self.playlist[self.guide_selection_index]
        
        # Recalculate page based on new index
        self.guide_page = self.guide_selection_index // self.guide_page_size
        self._render_guide()
        return None

    def _render_guide(self):
        """Renders the current page of the channel guide on the OSD."""
        if not self.is_guide_visible or not self.playlist:
            return

        start_index = self.guide_page * self.guide_page_size
        end_index = start_index + self.guide_page_size
        
        page_items = self.playlist[start_index:end_index]

        guide_text = "--- Channel Guide ---\n\n"
        for i, item in enumerate(page_items):
            full_index = start_index + i
            
            if 'series_name' in item:
                title = f"{item['series_name']} S{item['season']:02d}E{item['episode']:02d}"
            else:
                title = f"{item.get('title', 'Unknown')}"
            
            prefix = "> " if full_index == self.guide_selection_index else "  "
            guide_text += f"{prefix}{title}\n"
        
        guide_text += f"\n--- Item {self.guide_selection_index + 1} of {len(self.playlist)} ---"
        
        # Use a long duration to keep it on screen; it will be cleared manually
        formatted_text = f"{{\\an7}}{{\\fs_PROPERTY_ADD=15}}{guide_text}"
        self.player.osd_show_text(formatted_text, duration=3600 * 1000, level=3) 