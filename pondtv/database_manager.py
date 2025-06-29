import os
import yaml
from pondtv.utils import log
from pondtv.media_scanner import MediaScanner

class DatabaseManager:
    """Handles atomic loading and saving of the YAML database file."""
    
    def __init__(self, db_path: str):
        """
        Initializes the DatabaseManager.
        
        Args:
            db_path: The full path to the database YAML file.
        """
        self.db_path = db_path
        log.info(f"DatabaseManager initialized for path: {self.db_path}")

    def load_and_validate(self, media_path: str) -> dict:
        """
        Loads the database, validates its structure, and triggers a rescan if invalid.
        """
        log.info(f"Attempting to load and validate database from {self.db_path}")
        data = self.load()
        
        if not data or not self._is_valid(data):
            if not data:
                log.info("Database is empty, triggering initial scan.")
            else:
                log.warning("Database format is invalid or outdated. Triggering rescan.")
                self.backup() # Backup the bad database for debugging
            
            scanner = MediaScanner(media_path)
            data = scanner.scan()
            self.save(data)
        
        return data if data is not None else {}

    def _is_valid(self, data: dict) -> bool:
        """
        Performs a basic validation of the database structure.
        """
        if not isinstance(data, dict):
            log.warning("DB validation failed: Root is not a dictionary.")
            return False
        if 'movies' not in data or 'tv_shows' not in data:
            log.warning("DB validation failed: Missing 'movies' or 'tv_shows' keys.")
            return False
        
        # Check tv_shows structure
        for series_title, series_data in data.get('tv_shows', {}).items():
            if not isinstance(series_data, dict):
                log.warning(f"DB validation failed for TV Show '{series_title}': series data is not a dict.")
                return False
            if 'seasons' not in series_data:
                log.warning(f"DB validation failed for TV Show '{series_title}': missing 'seasons' key.")
                return False
        
        # Check movies structure
        for movie_title, movie_data in data.get('movies', {}).items():
            if not isinstance(movie_data, dict):
                log.warning(f"DB validation failed for Movie '{movie_title}': movie data is not a dict.")
                return False
            if 'filepath' not in movie_data:
                log.warning(f"DB validation failed for Movie '{movie_title}': missing 'filepath' key.")
                return False

        log.info("Database validation successful.")
        return True

    def load(self) -> dict:
        """
        Loads the database from the YAML file.
        
        Returns:
            A dictionary with the database contents, or an empty template if not found.
        """
        log.info(f"Attempting to load database from {self.db_path}")
        try:
            with open(self.db_path, 'r') as f:
                data = yaml.safe_load(f)
                log.info("Database loaded successfully.")
                # Ensure it returns a dict even if the file is empty
                return data if data is not None else {}
        except FileNotFoundError:
            log.warning("Database file not found. Returning empty structure.")
            return {}
        except Exception as e:
            log.error(f"Error loading database: {e}. Returning empty structure.")
            return {}

    def save(self, data: dict) -> bool:
        """
        Atomically saves data to the YAML file.
        
        This is a two-step process to prevent corruption on power loss:
        1. Write the new content to a temporary file.
        2. Atomically rename the temporary file to the original file name.
        
        Args:
            data: The dictionary to save.
            
        Returns:
            True if successful, False otherwise.
        """
        tmp_path = self.db_path + '.tmp'
        log.info(f"Attempting to save database to {self.db_path} via temp file {tmp_path}")
        try:
            with open(tmp_path, 'w') as f:
                yaml.dump(data, f, default_flow_style=False, indent=2)
            
            os.rename(tmp_path, self.db_path)
            log.info("Database saved successfully.")
            return True
        except Exception as e:
            log.error(f"Error saving database: {e}")
            # Clean up the temp file if it exists
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return False

    def backup(self) -> bool:
        """
        Creates a backup of the current database file.
        """
        backup_path = self.db_path + '.backup'
        log.info(f"Creating database backup at {backup_path}")
        try:
            current_data = self.load()
            if not current_data:
                log.warning("Database is empty, skipping backup.")
                return False

            # Reuse the atomic save logic for the backup
            tmp_path = backup_path + '.tmp'
            with open(tmp_path, 'w') as f:
                yaml.dump(current_data, f, default_flow_style=False, indent=2)
            
            os.rename(tmp_path, backup_path)
            log.info(f"Backup created successfully at {backup_path}")
            return True
        except Exception as e:
            log.error(f"Failed to create backup: {e}")
            return False

if __name__ == '__main__':
    # Test script for the DatabaseManager
    log.info("--- Running DatabaseManager Test ---")
    
    # Use a dummy path for testing
    test_db_path = 'test_database.yml'
    
    # 1. Create a DB Manager
    db_manager = DatabaseManager(test_db_path)
    
    # 2. Prepare some data
    test_data = {
        'movies': [{'title': 'Test Movie', 'year': 2024}],
        'series': [{'series_name': 'Test Show', 'episodes': []}]
    }
    
    # 3. Save the data
    log.info("Step 1: Saving initial data...")
    success = db_manager.save(test_data)
    if success:
        log.info("Save successful. Check for 'test_database.yml'.")
    else:
        log.error("Save failed.")

    # 4. Load the data back
    log.info("\nStep 2: Loading data back...")
    loaded_data = db_manager.load()
    if loaded_data == test_data:
        log.info("Load successful. Data matches.")
    else:
        log.error(f"Load failed. Data mismatch. Loaded: {loaded_data}")
        
    # 5. Create a backup
    log.info("\nStep 3: Creating a backup...")
    success = db_manager.backup()
    if success:
        log.info("Backup successful. Check for 'test_database.yml.backup'.")
    else:
        log.error("Backup failed.")
        
    # 6. Clean up the test files
    log.info("\n--- Test Complete ---")
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    if os.path.exists(test_db_path + '.backup'):
        os.remove(test_db_path + '.backup')
    log.info("Cleaned up test files.") 