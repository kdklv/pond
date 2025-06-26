# 🎯 PondTV Implementation Plan

> A detailed, robust, and corruption-proof implementation plan for the PondTV project, organized into comprehensive, AI-executable tasks.

---

## 📋 Core Principles for Implementation

*   **Data Integrity:** All file-write operations for the database (`media_library.yml`) and its backups MUST use an atomic write pattern (write to a temp file, then rename) to prevent corruption from abrupt power loss.
*   **Modularity:** Each component (USB, Database, Player, UI) will be a distinct Python class in its own file to ensure clean, maintainable code.
*   **Simplicity:** The "zen" philosophy applies to the code. We'll choose straightforward solutions that are easy to understand and maintain.

---

## ✅ Actionable Implementation Tasks

### **Task 1: [x] Foundation - Project Setup, USB Detection, and Corruption-Proof Database**

**Goal:** Establish the project's skeleton and create the two foundational components: detecting the media source and ensuring the database can be written to safely.

**Implementation Notes:**
- The project structure (`src`, `config`, `logs`) and `requirements.txt` have been created.
- A central logger was set up in `src/utils.py`.
- `src/database_manager.py` was implemented with a `DatabaseManager` class that performs atomic writes by saving to a `.tmp` file before renaming. This prevents database corruption on power loss.
- `src/usb_manager.py` was implemented with a `USBManager` class that uses `psutil` to find a connected drive containing a `Movies` directory marker.
- Both modules include `if __name__ == '__main__':` blocks for standalone testing.
- All dependencies were installed and tests were run successfully.

**Implementation Details:**
1.  **Project Structure:**
    -   Create the `pondtv/` directory with `src/`, `config/`, and `logs/` subdirectories.
    -   Inside `src/`, create empty files with class definitions for `usb_manager.py`, `database_manager.py`, and a `utils.py`.
    -   Create a `requirements.txt` file listing `PyYAML` and `psutil`.
2.  **USB Manager (`src/usb_manager.py`):**
    -   Create a `USBManager` class.
    -   Implement a `find_media_drive()` method that uses `psutil.disk_partitions()` to scan for connected USB drives.
    -   This method should identify the correct drive by looking for the presence of a specific marker, like a `.pondtv_marker` file or the `Movies/` directory.
    -   It should return the mount path of the media drive or `None` if not found.
    -   Add logging for all operations (e.g., "Scanning for USB drives...", "PondTV media drive found at /media/pi/USBDRIVE").
3.  **Database Manager (`src/database_manager.py`):**
    -   Create a `DatabaseManager` class that takes the path to the database file in its constructor.
    -   Implement a `save(data)` method. This method **MUST** be atomic.
        -   Write the YAML data to a temporary file (e.g., `media_library.yml.tmp`).
        -   Use `os.rename()` to atomically replace the original file with the temporary one. This is the key step for corruption-proofing.
    -   Implement a `load()` method that reads the YAML file and returns its content. It should handle `FileNotFoundError` gracefully, returning an empty template.
    -   Implement a `backup()` method that uses the same atomic `save` logic to create a `media_library.backup.yml`.

**Acceptance Criteria:**
- The project structure is created.
- Running `usb_manager.py` directly successfully prints the path to the connected USB drive.
- The `DatabaseManager` can successfully `load` and `save` a dictionary to a YAML file, and this operation can survive a simulated power loss (e.g., killing the script mid-write) without corrupting the original YAML file.

---

### **Task 2: [x] Media Scanner - Cataloging Movies and TV Shows**

**Goal:** Scan the media drive and use our corruption-proof database manager to create a structured catalog of all available content.

**Implementation Notes:**
- Implemented the `MediaScanner` class in `src/media_scanner.py`.
- The scanner uses regex to parse movie titles/years and series/season/episode numbers from filenames.
- It correctly identifies video files based on a list of common extensions.
- The `scan` method now loads the existing database first to create a lookup of old file data.
- When new media is scanned, it preserves the `status` and `resume_position` from the old database, ensuring user data is not lost on a re-scan.
- The final database structure for series was adjusted to a list of dictionaries as intended for the final YAML structure.
- A comprehensive test case was added to the `if __name__ == '__main__':` block, which builds a temporary file structure, runs a scan, modifies the DB, and re-scans to verify that state is preserved. The test passed successfully.

**Implementation Details:**
1.  **File System Scanning (`src/media_scanner.py`):**
    -   Create a `MediaScanner` class that takes a `DatabaseManager` instance and the root path of the media drive.
    -   Implement a `scan()` method that walks through the `Movies/` and `TV_Shows/` directories.
2.  **Metadata Parsing:**
    -   For files in `Movies/`, parse the filename to extract the movie `title` and `year`. A regex like `(.+?)\s*\((\d{4})\)` is a good starting point.
    -   For files in `TV_Shows/`, parse the directory structure and filenames to get the `series_name`, `season_number`, and `episode_number`. Assume a `ShowName/Season XX/Show.Name.SXXEXX.mkv` structure.
    -   The scanner should also look for subtitle files (`.srt`, `.vtt`, etc.) that have a similar name to the video file and add their paths to the metadata.
3.  **Database Population:**
    -   The `scan()` method should build a dictionary that matches the YAML structure defined in `TECH_STACK.md`.
    -   Once the scan is complete, it should call the `database_manager.save(data)` method to write the new catalog to `media_library.yml`.
    -   Implement logic to preserve the `status` and `resume_position` from an existing database if a rescan is performed. It should load the old data first and merge it with the new scan results.

**Acceptance Criteria:**
- Running the scanner successfully generates a `media_library.yml` on the USB drive.
- The YAML file correctly lists all movies with their titles and years.
- The YAML file correctly lists all TV shows, nested under their series, with season and episode numbers.
- Subtitle files are correctly associated with their corresponding video files.
- Re-running the scan does not overwrite the `status` of existing entries.

---

### **Task 3: [x] Playback Engine - Smart Playlist and MPV Integration**

**Goal:** Read the media database, create an intelligent playback queue, and get the first video playing on the screen using `mpv`.

**Implementation Notes:**
- Added `python-mpv` to `requirements.txt` and installed it.
- Implemented `PlayerController` in `src/player_controller.py`. It initializes an `mpv` instance configured for fullscreen, GUI-less playback. It includes a `play()` method that blocks until playback is finished. A test block requiring manual user confirmation (closing the mpv window) was included.
- Implemented `PlaylistEngine` in `src/playlist_engine.py`. Its `create_playlist()` method correctly filters out "Seen" items and, crucially, only adds the single *next* unseen episode for each TV series, preventing future episodes from populating the queue. It then shuffles all eligible items.
- The `PlaylistEngine` test passed successfully, confirming the smart selection logic is correct.

**Implementation Details:**
1.  **Playlist Engine (`src/playlist_engine.py`):**
    -   Create a `PlaylistEngine` class that takes the loaded database content.
    -   Implement a `create_playlist()` method.
    -   This method should first filter out all content marked as `"Seen"`.
    -   For each TV series, it should only add the *next unseen episode* to the eligible pool of content (e.g., if S01E02 is unseen, S01E03 is ignored).
    -   All unseen movies are added to the eligible pool.
    -   Finally, it should shuffle this final pool of eligible items and return it as a list.
2.  **Player Controller (`src/player_controller.py`):**
    -   Create a `PlayerController` class.
    -   Add an `initialize_mpv()` method that configures `mpv` for fullscreen, no-GUI playback. The `python-mpv` library should be used here.
    -   Implement a `play(media_item)` method that takes an item from the playlist and tells `mpv` to play its `filepath`.
    -   Set up `mpv` event bindings, specifically for `end-file`, which will be crucial for auto-playing the next item in a later task.

**Acceptance Criteria:**
- The `PlaylistEngine` correctly generates a shuffled list containing only unseen movies and the *next* unseen episode of each series.
- The `PlayerController` can successfully launch `mpv` in fullscreen.
- A main script can load the DB, create a playlist, take the first item, and play it. The video appears on screen.

---

### **Task 4: [ ] Interactive Controls - Input Handling and Playback State**

**Goal:** Bring the player to life by enabling user controls for navigation, and ensure the user's progress is saved back to the database atomically.

**Implementation Details:**
1.  **Input Handler (`src/input_handler.py`):**
    -   Create an `InputHandler` class. This is a complex task; using a library like `pynput` is recommended for listening to keyboard events system-wide without needing a focused window.
    -   Map keys to actions:
        -   `Right Arrow`: Next video
        -   `Right Mouse click`: Next video
        -   `Left Arrow`: Previous video / Restart current
        -   `Left Mouse click`: Previous video / Restart current
        -   `Spacebar`: Play/Pause
        -   `S`: Mark current video as "Seen"
        -   `Up Arrow`: Volume up
        -   `Down Arrow`: Volume down
        -   `Scroll Up`: Volume up
        -   `Scroll Down`: Volume down




        
    -   The handler should use a callback or queue system to communicate these actions back to the main application loop.
2.  **Connecting Controls to Player:**
    -   The `PlayerController` needs methods to handle these actions: `toggle_pause()`, `seek()`, `stop()`, etc.
    -   The main application loop will receive an action from the `InputHandler` and call the appropriate method on the `PlayerController` or `PlaylistEngine`.
3.  **Saving Playback State (Atomically):**
    -   When the `Next` action is triggered or a video finishes, the application must:
        -   Update the status of the video that just played (e.g., to "Seen").
        -   Get the current playback position from `mpv` and store it in `resume_position`.
        -   Load the latest database state into memory.
        -   Update the dictionary in memory with the new status/resume position.
        -   Call the `database_manager.save()` method to write the changes back to disk atomically. This is critical for saving progress reliably.

**Acceptance Criteria:**
- Pressing the right arrow key stops the current video and starts the next one from the playlist.
- Play/pause works as expected.
- Marking a video as "Seen" updates the `media_library.yml` file correctly and prevents it from appearing in the next playlist.
- Stopping a video mid-way saves the resume position to the YAML file.

---

### **Task 5: [ ] User Interface - Channel Guide and Title Overlays**

**Goal:** Implement the two key UI features that enhance the user experience: the "channel guide" and the temporary title overlay.

**Implementation Details:**
1.  **UI Manager (`src/ui_manager.py`):**
    -   Create a `UIManager` class that takes the `PlayerController`'s `mpv` instance as an argument.
2.  **Title Overlay:**
    -   Implement a `show_title_overlay(media_item)` method.
    -   This method will use `mpv.osd_show_text()` to display the `title` (and episode info for series) on screen.
    -   It should be configured with a duration (e.g., 3-5 seconds) after which it automatically disappears.
    -   This should be called every time a new video starts playing.
3.  **Channel Guide:**
    -   This is the more complex part. The `InputHandler` needs to detect the `I` or `P` key.
    -   When pressed, the `UIManager`'s `show_channel_guide()` method is called.
    -   This method will display the list of all playable titles (from the `PlaylistEngine`) using the `mpv` OSD. This will require some formatting logic to make a clean, scrollable-looking list.
    -   The `InputHandler` must switch context. The `Up/Down` arrow keys should now scroll the selection in the guide, and `Enter` should select an item.
    -   When an item is selected, the guide is hidden, and the `PlayerController` is instructed to play the selected item.

**Acceptance Criteria:**
- When a video starts, its title briefly appears on screen.
- Pressing 'I' shows a list of available content.
- While the list is visible, arrow keys change the highlighted item, and Enter plays it.
- The UI is rendered clearly using `mpv`'s On-Screen Display.

---

### **Task 6: [ ] Final Assembly - Main Loop, System Autostart, and Error Handling**

**Goal:** Tie all the components together into a single, cohesive application that can run automatically on boot and handle common errors gracefully.

**Implementation Details:**
1.  **Main Application (`src/main.py`):**
    -   Create the main entry point for the application.
    -   This script will orchestrate the entire process:
        -   Initialize logging.
        -   Initialize the `USBManager` and find the drive. If not found, enter a loop and wait.
        -   Initialize the `DatabaseManager`.
        -   Run the `MediaScanner` if the database is missing or outdated.
        -   Load the database, initialize the `PlaylistEngine`.
        -   Initialize the `PlayerController`, `InputHandler`, and `UIManager`.
        -   Start the first video and enter the main input-handling loop.
2.  **System Integration:**
    -   Create a `pondtv.service` file in the `config/` directory. This `systemd` unit file will define how to start the `main.py` script on boot.
    -   Create a simple `install.sh` script that copies the `systemd` service to the correct location (`/etc/systemd/system/`) and enables it.
3.  **Error Handling:**
    -   Add `try...except` blocks around critical operations.
    -   Handle `FileNotFoundError` if a media file is in the DB but missing from the disk (skip and log).
    -   Handle `mpv` crashes (log the error and try to restart the player).
    -   If the USB is unplugged mid-operation, the app should detect this and return to the "waiting for drive" state.

**Acceptance Criteria:**
- The application starts and runs correctly when `python src/main.py` is executed.
- The `install.sh` script successfully sets up the `systemd` service.
- After a reboot, PondTV starts automatically and begins playback.
- The application does not crash if a media file is missing; it logs the error and moves on.

---

## 📊 Data Structures & Key Components

### **Core Data Models**
```yaml
# media_library.yml structure
movies:
  - filepath: "Movies/Inception (2010).mkv"
    title: "Inception"
    year: 2010
    status: "Unseen"
    resume_position: null
    last_watched: null
    subtitles: ["Movies/Inception (2010).srt"]

series:
  - series_name: "The Office"
    episodes:
      - filepath: "TV_Shows/The Office/Season 01/The Office - S01E01 - Pilot.mp4"
        title: "Pilot"
        season: 1
        episode: 1
        status: "Unseen"
        resume_position: null
        last_watched: null
```

### **Key Classes & Methods**
```python
# Core architecture overview
class USBManager:
    - detect_drives() -> List[str]
    - mount_drive(path: str) -> bool
    - validate_structure(path: str) -> bool

class MediaDatabase:
    - load() -> dict
    - save(data: dict) -> bool
    - backup() -> bool
    - validate() -> bool

class PlaylistEngine:
    - compile_playlist() -> List[MediaItem]
    - get_next_episode(series: str) -> MediaItem
    - shuffle_movies() -> List[MediaItem]
    - update_status(item: MediaItem, status: str)

class PlayerController:
    - initialize_mpv() -> bool
    - play(filepath: str) -> bool
    - handle_events() -> None
    - get_position() -> float
```

---

**Implementation Strategy:** Each task is designed to be completable in a single focused development session, with clear inputs/outputs and minimal dependencies on incomplete components. Tasks build incrementally toward the final zen media experience.