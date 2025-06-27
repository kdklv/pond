import os
import yaml
from .utils import log

class ConfigManager:
    """Manages loading and accessing the application configuration."""

    def __init__(self, media_path: str):
        """
        Initializes the ConfigManager.

        Args:
            media_path: The root path of the media drive.
        """
        self.config_path = os.path.join(media_path, 'config.yml')
        self.log = log
        self._defaults = {
            'ui': {
                'title_overlay_duration': 5,
                'guide_page_size': 10,
            },
            'player': {
                'volume_default': 70,
                'volume_step': 5,
            }
        }
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Loads the config file, creating it if it doesn't exist."""
        if not os.path.exists(self.config_path):
            self.log.info("No config.yml found. Creating one with default values.")
            self._create_default_config()

        try:
            with open(self.config_path, 'r') as f:
                user_config = yaml.safe_load(f) or {}
            
            # Merge user config with defaults to ensure all keys are present
            config = self._defaults.copy()
            config.update(user_config)
            
            self.log.info("Configuration loaded successfully.")
            return config
        except Exception as e:
            self.log.error(f"Error loading config.yml: {e}. Using default values.")
            return self._defaults

    def _create_default_config(self):
        """Creates the default config.yml file."""
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self._defaults, f, default_flow_style=False, indent=2)
            self.log.info(f"Default config.yml created at {self.config_path}")
        except Exception as e:
            self.log.error(f"Failed to create default config file: {e}")

    def get(self, key_path: str, default=None):
        """
        Retrieves a value from the config using a dot-separated path.
        
        Example: get('ui.title_overlay_duration')
        """
        keys = key_path.split('.')
        value = self.config
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            self.log.warning(f"Config key '{key_path}' not found. Returning default: {default}")
            return default

if __name__ == '__main__':
    log.info("--- Running ConfigManager Test ---")
    
    # Create a dummy environment
    dummy_path = 'temp_config_test'
    os.makedirs(dummy_path, exist_ok=True)
    
    # 1. Test creation of default config
    log.info("\nStep 1: Testing with no existing config file...")
    config_manager = ConfigManager(dummy_path)
    assert os.path.exists(os.path.join(dummy_path, 'config.yml'))
    assert config_manager.get('ui.title_overlay_duration') == 5
    log.info("Default config created and loaded correctly.")

    # 2. Test reading a custom value
    log.info("\nStep 2: Testing with a custom config value...")
    custom_config = {'ui': {'title_overlay_duration': 10}}
    with open(os.path.join(dummy_path, 'config.yml'), 'w') as f:
        yaml.dump(custom_config, f)
    
    config_manager = ConfigManager(dummy_path)
    assert config_manager.get('ui.title_overlay_duration') == 10
    assert config_manager.get('player.volume_default') == 70 # Should still have default
    log.info("Custom config value loaded correctly.")

    # 3. Cleanup
    import shutil
    shutil.rmtree(dummy_path)
    log.info("\n--- Test Complete ---") 