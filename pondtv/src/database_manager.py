import os
import yaml
import threading
from .utils import log

class DatabaseManager:
    """Handles atomic loading and saving of the YAML database file with thread safety."""
    
    def __init__(self, db_path: str):
        """
        Initializes the DatabaseManager.
        
        Args:
            db_path: The full path to the database YAML file.
        """
        self.db_path = db_path
        self._lock = threading.RLock()  # Reentrant lock for nested calls
        log.info(f"DatabaseManager initialized for path: {self.db_path}")

    def load(self) -> dict:
        """
        Loads the database from the YAML file in a thread-safe manner.
        
        Returns:
            A dictionary with the database contents, or an empty template if not found.
        """
        with self._lock:
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
        Atomically saves data to the YAML file in a thread-safe manner.
        
        This is a two-step process to prevent corruption on power loss:
        1. Write the new content to a temporary file.
        2. Atomically rename the temporary file to the original file name.
        
        Args:
            data: The dictionary to save.
            
        Returns:
            True if successful, False otherwise.
        """
        with self._lock:
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
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass  # Best effort cleanup
                return False

    def update_item_status(self, filepath: str, status: str, resume_position: int | None = None) -> bool:
        """
        Thread-safe method to update a single item's status and resume position.
        
        Args:
            filepath: The filepath of the item to update
            status: New status ('Seen' or 'Unseen')
            resume_position: New resume position in seconds (optional)
            
        Returns:
            True if item was found and updated, False otherwise
        """
        with self._lock:
            try:
                db_content = self.load()
                item_found = False
                
                # Check movies
                for movie in db_content.get('movies', []):
                    if movie['filepath'] == filepath:
                        movie['status'] = status
                        if resume_position is not None:
                            movie['resume_position'] = resume_position
                        item_found = True
                        break
                
                # Check series episodes if not found in movies
                if not item_found:
                    for series in db_content.get('series', []):
                        for episode in series.get('episodes', []):
                            if episode['filepath'] == filepath:
                                episode['status'] = status
                                if resume_position is not None:
                                    episode['resume_position'] = resume_position
                                item_found = True
                                break
                        if item_found:
                            break
                
                if item_found:
                    success = self.save(db_content)
                    if success:
                        log.info(f"Updated status for '{filepath}' to '{status}'" + 
                                (f" with resume position {resume_position}s" if resume_position else ""))
                    return success
                else:
                    log.warning(f"Could not find item '{filepath}' in database to update status.")
                    return False
                    
            except Exception as e:
                log.error(f"Failed to update item status: {e}")
                return False

    def backup(self) -> bool:
        """
        Creates a backup of the current database file in a thread-safe manner.
        """
        with self._lock:
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