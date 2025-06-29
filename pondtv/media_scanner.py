import os
import re
from pondtv.utils import log
from pondtv.database_manager import DatabaseManager

class MediaScanner:
    """
    Scans a media drive to find and catalog movies and TV series,
    handling complex and messy file structures.
    """
    VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov"}
    MIN_FILE_SIZE_MB = 50  # Files smaller than this are likely samples
    YEAR_REGEX = re.compile(r'\(?(\d{4})\)?')
    SEASON_EPISODE_REGEX = re.compile(
        r'[._\s-](s|season)?(\d{1,2})[ex](\d{1,3})[._\s-]', re.I
    )
    SEASON_REGEX = re.compile(r'[._\s-](s|season)(\d{1,2})[._\s-]', re.I)
    EPISODE_REGEX = re.compile(r'[._\s-](e|ep|episode|\dof)(\d{1,3})[._\s-]', re.I)

    def __init__(self, media_path: str, db_manager: DatabaseManager):
        self.media_path = media_path
        self.db_manager = db_manager
        log.info("MediaScanner initialized.")

    def scan(self):
        """Performs a full scan of the media drive and saves to the database."""
        log.info("Starting media scan...")
        db_content = {'movies': [], 'series': []}
        
        movies_path = os.path.join(self.media_path, "Movies")
        if os.path.exists(movies_path):
            db_content['movies'] = self._scan_movies(movies_path)

        shows_path = os.path.join(self.media_path, "Shows")
        if os.path.exists(shows_path):
            db_content['series'] = self._scan_series(shows_path)
            
        self.db_manager.save(db_content)
        log.info("Media scan complete and database saved.")

    def _is_valid_video(self, file_path: str) -> bool:
        """Checks if a file is a valid, non-sample video file."""
        if not any(file_path.lower().endswith(ext) for ext in self.VIDEO_EXTENSIONS):
            return False
        
        # Ignore samples, trailers, etc.
        if re.search(r'[._\s-](sample|trailer|extra)[._\s-]', file_path, re.I):
            return False
            
        try:
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if size_mb < self.MIN_FILE_SIZE_MB:
                log.info(f"Ignoring small file: {file_path} ({size_mb:.2f}MB)")
                return False
        except OSError:
            return False # File might not be accessible
            
        return True

    def _clean_name(self, name: str) -> str:
        """Cleans up a file or folder name for display."""
        name = self.YEAR_REGEX.sub('', name) # Remove year
        # Remove common release tags
        name = re.sub(r'\[.*?\]|\(.*?\)|1080p|720p|bluray|webrip|h264|x265|aac', '', name, flags=re.I)
        name = name.replace('.', ' ').replace('_', ' ').strip()
        # Capitalize and clean up whitespace
        return ' '.join(word.capitalize() for word in name.split()).strip()

    def _scan_movies(self, movies_path: str) -> list:
        """Scans the 'Movies' directory."""
        movies = []
        log.info(f"Scanning for movies in: {movies_path}")
        
        for movie_dir_name in os.listdir(movies_path):
            movie_dir_path = os.path.join(movies_path, movie_dir_name)
            if not os.path.isdir(movie_dir_path):
                continue

            log.info(f"Processing movie folder: {movie_dir_name}")
            
            # Find the largest video file in the directory tree
            main_video_file = None
            max_size = 0
            for root, _, files in os.walk(movie_dir_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if self._is_valid_video(file_path):
                        size = os.path.getsize(file_path)
                        if size > max_size:
                            max_size = size
                            main_video_file = file_path
            
            if main_video_file:
                year_match = self.YEAR_REGEX.search(movie_dir_name)
                year = int(year_match.group(1)) if year_match else None
                title = self._clean_name(movie_dir_name)

                movies.append({
                    'title': title,
                    'year': year,
                    'file_path': os.path.relpath(main_video_file, self.media_path),
                    'status': 'Unseen',
                    'resume_position': 0
                })
        return movies

    def _scan_series(self, shows_path: str) -> list:
        """Scans the 'Shows' directory."""
        series_list = []
        log.info(f"Scanning for TV series in: {shows_path}")

        for show_dir_name in os.listdir(shows_path):
            show_dir_path = os.path.join(shows_path, show_dir_name)
            if not os.path.isdir(show_dir_path):
                continue
                
            show_title = self._clean_name(show_dir_name)
            log.info(f"Processing show: {show_title} ({show_dir_name})")
            
            episodes = []
            for root, _, files in os.walk(show_dir_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    if not self._is_valid_video(file_path):
                        continue

                    season_num, episode_num = self._parse_episode_info(file_path, root, show_dir_path)
                    
                    if episode_num is not None:
                        episodes.append({
                            'season': season_num,
                            'episode': episode_num,
                            'file_path': os.path.relpath(file_path, self.media_path),
                            'status': 'Unseen',
                            'resume_position': 0
                        })
            
            if episodes:
                series_list.append({
                    'series_name': show_title,
                    'episodes': sorted(episodes, key=lambda e: (e['season'], e['episode']))
                })
                
        return series_list

    def _parse_episode_info(self, file_path: str, root_path: str, show_path: str) -> tuple[int | None, int | None]:
        """Attempts to extract season and episode number from file/path."""
        filename = os.path.basename(file_path)
        
        # Try SxxExx format first
        match = self.SEASON_EPISODE_REGEX.search(filename)
        if match:
            return int(match.group(2)), int(match.group(3))

        # Check path for season folder
        season_num = 1
        rel_path = os.path.relpath(root_path, show_path)
        season_match = re.search(r'(s|season)[\s_.]?(\d{1,2})', rel_path, re.I)
        if season_match:
            season_num = int(season_match.group(2))

        # Check filename for episode number
        ep_match = self.EPISODE_REGEX.search(filename)
        if ep_match:
            return season_num, int(ep_match.group(2))
        
        # For single-video shows/documentaries, assign as S01E01
        if root_path == show_path:
             # Check if it's the only video file in the show's root
            videos_in_root = [f for f in os.listdir(show_path) if self._is_valid_video(os.path.join(show_path, f))]
            if len(videos_in_root) == 1:
                log.info(f"Treating as single-video special: {filename}")
                return 1, 1

        log.warning(f"Could not determine episode number for: {filename}")
        return season_num, None # Could not determine episode


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