import os
import re
from .utils import log
from .database_manager import DatabaseManager

class MediaScanner:
    """Scans the media drive and builds/updates the YAML database."""

    def __init__(self, root_path: str, db_manager: DatabaseManager):
        """
        Initializes the MediaScanner.

        Args:
            root_path: The root path of the media drive to scan.
            db_manager: An instance of DatabaseManager to handle DB operations.
        """
        self.root_path = root_path
        self.db_manager = db_manager
        self.video_formats = ('.mp4', '.mkv', '.avi', '.mov', '.m4v')
        self.movie_regex = re.compile(r'(.+?)\s*\((\d{4})\)')
        self.series_regex = re.compile(r'.*?s(\d{1,2})e(\d{1,2})', re.IGNORECASE)
        log.info(f"MediaScanner initialized for path: {self.root_path}")

    def scan(self):
        """
        Performs a full scan of the media directories and updates the database.
        It preserves the 'status' and 'resume_position' of existing entries.
        """
        log.info("Starting media scan...")
        
        # Load the existing database to preserve state
        old_db_data = self.db_manager.load()
        old_movies = {m['filepath']: m for m in old_db_data.get('movies', [])}
        old_series_episodes = {e['filepath']: e for s in old_db_data.get('series', []) for e in s.get('episodes', [])}

        new_db_data = {'movies': [], 'series': {}}

        # Scan Movies
        movies_path = os.path.join(self.root_path, 'Movies')
        if os.path.isdir(movies_path):
            for filename in os.listdir(movies_path):
                if filename.lower().endswith(self.video_formats):
                    filepath = os.path.join('Movies', filename).replace('\\', '/')
                    movie_data = old_movies.get(filepath, {})
                    
                    match = self.movie_regex.match(os.path.splitext(filename)[0])
                    if match:
                        title, year = match.groups()
                        movie_data.update({
                            'filepath': filepath,
                            'title': title.strip(),
                            'year': int(year),
                            'status': movie_data.get('status', 'Unseen'),
                            'resume_position': movie_data.get('resume_position', None)
                        })
                        new_db_data['movies'].append(movie_data)

        # Scan TV Shows
        shows_path = os.path.join(self.root_path, 'TV_Shows')
        if os.path.isdir(shows_path):
            for series_name in os.listdir(shows_path):
                series_path = os.path.join(shows_path, series_name)
                if os.path.isdir(series_path):
                    for season_folder in os.listdir(series_path):
                        season_path = os.path.join(series_path, season_folder)
                        if os.path.isdir(season_path):
                            for episode_filename in os.listdir(season_path):
                                if episode_filename.lower().endswith(self.video_formats):
                                    filepath = os.path.join('TV_Shows', series_name, season_folder, episode_filename).replace('\\', '/')
                                    episode_data = old_series_episodes.get(filepath, {})
                                    
                                    match = self.series_regex.match(episode_filename)
                                    if match:
                                        season_num, episode_num = match.groups()
                                        
                                        if series_name not in new_db_data['series']:
                                            new_db_data['series'][series_name] = []

                                        episode_data.update({
                                            'filepath': filepath,
                                            'season': int(season_num),
                                            'episode': int(episode_num),
                                            'status': episode_data.get('status', 'Unseen'),
                                            'resume_position': episode_data.get('resume_position', None)
                                        })
                                        new_db_data['series'][series_name].append(episode_data)
        
        # Convert series dict to list of dicts for final structure
        final_series_list = [{'series_name': name, 'episodes': eps} for name, eps in new_db_data['series'].items()]
        
        final_db_data = {'movies': new_db_data['movies'], 'series': final_series_list}

        self.db_manager.save(final_db_data)
        log.info("Media scan complete and database updated.")


if __name__ == '__main__':
    import shutil

    log.info("--- Running MediaScanner Test ---")
    
    # 1. Setup a dummy environment
    dummy_media_path = 'temp_media_for_test'
    dummy_db_path = os.path.join(dummy_media_path, 'test_media_library.yml')
    
    # Create dummy directories
    os.makedirs(os.path.join(dummy_media_path, 'Movies'), exist_ok=True)
    os.makedirs(os.path.join(dummy_media_path, 'TV_Shows', 'Test Show', 'Season 1'), exist_ok=True)
    
    # Create dummy files
    open(os.path.join(dummy_media_path, 'Movies', 'The Matrix (1999).mkv'), 'a').close()
    open(os.path.join(dummy_media_path, 'TV_Shows', 'Test Show', 'Season 1', 'Test.Show.S01E01.mp4'), 'a').close()
    open(os.path.join(dummy_media_path, 'TV_Shows', 'Test Show', 'Season 1', 'Test.Show.S01E02.mp4'), 'a').close()

    # 2. Run the first scan
    log.info("\nStep 1: Performing initial scan...")
    db_manager = DatabaseManager(dummy_db_path)
    scanner = MediaScanner(dummy_media_path, db_manager)
    scanner.scan()
    
    # Verify first scan
    db_content = db_manager.load()
    log.info(f"DB content after first scan: {db_content}")
    assert len(db_content.get('movies', [])) == 1
    assert len(db_content.get('series', [])[0].get('episodes', [])) == 2
    assert db_content['movies'][0]['title'] == 'The Matrix'
    log.info("Initial scan results are correct.")
    
    # 3. Modify the database to simulate 'seen' status and rescan
    log.info("\nStep 2: Simulating 'seen' status and re-scanning...")
    db_content['movies'][0]['status'] = 'Seen'
    db_manager.save(db_content)
    
    # Add a new movie and run scan again
    open(os.path.join(dummy_media_path, 'Movies', 'Inception (2010).mkv'), 'a').close()
    scanner.scan()
    
    # Verify second scan
    db_content_after_rescan = db_manager.load()
    log.info(f"DB content after second scan: {db_content_after_rescan}")
    assert len(db_content_after_rescan.get('movies', [])) == 2
    
    # Check that the 'Seen' status of The Matrix was preserved
    matrix_movie = next(m for m in db_content_after_rescan['movies'] if m['title'] == 'The Matrix')
    assert matrix_movie['status'] == 'Seen'
    log.info("'Seen' status was preserved correctly after re-scan.")
    
    # 4. Cleanup
    log.info("\n--- Test Complete ---")
    shutil.rmtree(dummy_media_path)
    log.info("Cleaned up dummy media environment.") 