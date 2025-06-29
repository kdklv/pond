import random
from pondtv.utils import log

class PlaylistEngine:
    """Creates an intelligent, shuffled playlist from the media database."""

    def __init__(self, db_content: dict):
        """
        Initializes the PlaylistEngine.

        Args:
            db_content: The full database content as a dictionary.
        """
        self.db_content = db_content
        log.info("PlaylistEngine initialized.")

    def create_playlist(self) -> list:
        """
        Creates a smart-shuffled playlist.

        - Filters out all content marked as "Seen".
        - For each TV series, only adds the *next* unseen episode.
        - Shuffles all eligible movies and series episodes together.

        Returns:
            A shuffled list of media item dictionaries to be played.
        """
        log.info("Creating a new smart playlist...")
        eligible_content = []

        # Process movies
        unseen_movies = [
            movie for movie in self.db_content.get('movies', [])
            if movie.get('status') == 'Unseen'
        ]
        eligible_content.extend(unseen_movies)
        log.info(f"Added {len(unseen_movies)} unseen movies to the playlist.")

        # Process series
        for series in self.db_content.get('series', []):
            # Sort episodes to find the next unseen one
            episodes = sorted(series.get('episodes', []), key=lambda e: (e.get('season', 0), e.get('episode', 0)))
            
            next_unseen_episode = None
            for episode in episodes:
                if episode.get('status') == 'Unseen':
                    next_unseen_episode = episode
                    break  # Found the first unseen one, stop looking for this series
            
            if next_unseen_episode:
                # Add series context to the episode for easier identification
                next_unseen_episode['series_name'] = series.get('series_name')
                eligible_content.append(next_unseen_episode)
                log.info(f"Added next unseen episode for '{series.get('series_name')}': S{next_unseen_episode['season']}E{next_unseen_episode['episode']}")

        log.info(f"Total eligible items for shuffling: {len(eligible_content)}")
        random.shuffle(eligible_content)
        log.info("Playlist shuffled.")
        
        return eligible_content

if __name__ == '__main__':
    log.info("--- Running PlaylistEngine Test ---")

    # 1. Create a dummy database
    dummy_db = {
        'movies': [
            {'title': 'Seen Movie', 'filepath': 'm1.mkv', 'status': 'Seen'},
            {'title': 'Unseen Movie 1', 'filepath': 'm2.mkv', 'status': 'Unseen'},
            {'title': 'Unseen Movie 2', 'filepath': 'm3.mkv', 'status': 'Unseen'},
        ],
        'series': [
            {
                'series_name': 'Finished Show',
                'episodes': [
                    {'season': 1, 'episode': 1, 'filepath': 's1e1.mkv', 'status': 'Seen'},
                    {'season': 1, 'episode': 2, 'filepath': 's1e2.mkv', 'status': 'Seen'},
                ]
            },
            {
                'series_name': 'Ongoing Show',
                'episodes': [
                    {'season': 1, 'episode': 1, 'filepath': 's2e1.mkv', 'status': 'Seen'},
                    {'season': 1, 'episode': 2, 'filepath': 's2e2.mkv', 'status': 'Unseen'}, # This should be picked
                    {'season': 1, 'episode': 3, 'filepath': 's2e3.mkv', 'status': 'Unseen'}, # This should be ignored
                ]
            },
            {
                'series_name': 'New Show',
                'episodes': [
                    {'season': 1, 'episode': 1, 'filepath': 's3e1.mkv', 'status': 'Unseen'}, # This should be picked
                ]
            }
        ]
    }
    
    log.info("Step 1: Initializing engine with dummy data...")
    engine = PlaylistEngine(dummy_db)
    
    log.info("Step 2: Creating playlist...")
    playlist = engine.create_playlist()
    
    log.info(f"Generated Playlist (length {len(playlist)}):")
    for item in playlist:
        if 'series_name' in item:
            log.info(f"- {item['series_name']} S{item['season']}E{item['episode']}")
        else:
            log.info(f"- {item['title']}")
            
    # 3. Assertions to verify the logic
    assert len(playlist) == 4, "Playlist should contain 4 items"
    
    titles_in_playlist = {item.get('title') or item.get('filepath') for item in playlist}
    assert 'Unseen Movie 1' in titles_in_playlist
    assert 'Unseen Movie 2' in titles_in_playlist
    assert 's2e2.mkv' in titles_in_playlist # Next unseen from Ongoing Show
    assert 's3e1.mkv' in titles_in_playlist # Next unseen from New Show
    
    assert 'Seen Movie' not in titles_in_playlist
    assert 's1e1.mkv' not in titles_in_playlist # From finished show
    assert 's1e2.mkv' not in titles_in_playlist # From finished show
    assert 's2e3.mkv' not in titles_in_playlist # Blocked by s2e2

    log.info("Assertions passed. The playlist logic is correct.")
    log.info("--- Test Complete ---") 