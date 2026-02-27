import random
from pondtv.utils import log


class PlaylistEngine:
    """Creates an intelligent, shuffled playlist from the media database."""

    def __init__(self, db_content: dict):
        self.db_content = db_content
        log.info("PlaylistEngine initialized.")

    def create_playlist(self) -> list[dict]:
        """
        Builds a smart-shuffled playlist from the database.

        - Skips everything marked as 'Seen'.
        - For each TV show, only adds the *next* unseen episode (enforces
          watching in order, one episode at a time).
        - Shuffles movies and TV episodes together.

        The database schema this engine expects:

            movies:
              Movie Title:
                filepath: ...
                status: Unseen | Seen
                resume_position: 0

            tv_shows:
              Show Title:
                seasons:
                  Season 01:
                    episodes:
                      - season: 1
                        episode: 1
                        filepath: ...
                        status: Unseen | Seen
                        resume_position: 0
        """
        log.info("Creating a new smart playlist...")
        playlist = []

        # --- Movies ---
        # movies is a dict keyed by title; iterate over values.
        movies: dict = self.db_content.get('movies', {})
        for title, movie in movies.items():
            if movie.get('status') == 'Seen':
                continue
            entry = dict(movie)
            entry['title'] = title
            playlist.append(entry)
        log.info(f"Added {len(playlist)} unseen movies.")

        # --- TV shows ---
        # tv_shows is a dict keyed by show title.
        # Each show has seasons (dict keyed by "Season NN"), each season has
        # an episodes list sorted by episode number.
        tv_shows: dict = self.db_content.get('tv_shows', {})
        for show_title, show_data in tv_shows.items():
            seasons: dict = show_data.get('seasons', {})

            # Flatten all episodes across seasons in order so we can find
            # the first unseen one regardless of season boundaries.
            all_episodes = []
            for season_key in sorted(seasons.keys()):
                all_episodes.extend(seasons[season_key].get('episodes', []))

            for ep in all_episodes:
                if ep.get('status') != 'Seen':
                    entry = dict(ep)
                    entry['show_title'] = show_title
                    playlist.append(entry)
                    log.info(
                        f"Added next episode for '{show_title}': "
                        f"S{ep.get('season', 0):02d}E{ep.get('episode', 0):02d}"
                    )
                    break  # Only the next unseen episode per show

        log.info(f"Total items before shuffle: {len(playlist)}")
        random.shuffle(playlist)
        return playlist
