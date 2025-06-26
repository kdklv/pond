# 🛠️ PondTV Technical Implementation Guide

> Comprehensive tech stack and implementation roadmap for the zen media experience

---

## 🎯 Core Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     PondTV System                           │
├─────────────────────────────────────────────────────────────┤
│  Boot Sequence → Media Scanner → Playlist Engine → Player   │
│       ↓              ↓              ↓             ↓        │
│   Auto-mount    CSV Database    Smart Shuffle    mpv       │
│   USB Drive     Generation      Logic            Control   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Technology Stack

### **Core Runtime**
- **OS:** Raspberry Pi OS Lite (minimal, fast boot)
- **Python:** 3.9+ (primary language)
- **Media Player:** `mpv` with Python bindings (`python-mpv`)
- **File System:** Auto-mount USB via `udev` rules

### **Key Libraries**
```python
# Core Dependencies
PyYAML          # YAML manipulation for the database
python-mpv      # mpv player Python bindings  
watchdog        # File system monitoring
psutil          # System resource monitoring

# Optional/Future
mutagen         # Audio/video metadata extraction
Pillow          # Image processing for thumbnails
```

### **System Integration**
- **Autostart:** systemd service (`pondtv.service`)
- **Input Handling:** Direct keyboard/mouse event capture
- **Storage:** USB auto-mount with fallback detection
- **Database:** Plain YAML file (`media_library.yml`)
- **Logging:** Python logging to `/var/log/pondtv.log`

---

## 🏗️ High-Level System Components

### **1. Boot & Initialization (`boot_manager.py`)**
```python
class BootManager:
    """Handles system startup and USB detection"""
    - detect_usb_drives()
    - mount_media_drive() 
    - validate_directory_structure()
    - initialize_logging()
    - start_main_application()
```

### **2. Media Scanner (`media_scanner.py`)**
```python
class MediaScanner:
    """Scans USB drive and builds/updates YAML database"""
    - scan_directory_tree()
    - extract_metadata_from_filename()
    - detect_subtitles()
    - generate_yaml_database()
    - update_existing_entries()
    - backup_seen_status()
```

### **3. Playlist Engine (`playlist_engine.py`)**
```python
class PlaylistEngine:
    """Smart shuffling logic with series awareness"""
    - load_media_database()
    - filter_unseen_content()
    - compile_eligible_playlist()
    - smart_shuffle_algorithm()
    - get_next_episode_in_series()
    - update_seen_status()
```

### **4. Media Player Controller (`player_controller.py`)**
```python
class PlayerController:
    """mpv integration and playback management"""
    - initialize_mpv_player()
    - load_and_play_media()
    - handle_playback_events()
    - detect_completion()
    - manage_resume_positions()
    - overlay_title_display()
```

### **5. Input Handler (`input_handler.py`)**
```python
class InputHandler:
    """Keyboard/mouse input processing"""
    - capture_system_input()
    - handle_navigation_keys()
    - process_volume_controls()
    - manage_seek_operations()
    - trigger_channel_surfing()
```

### **6. UI Manager (`ui_manager.py`)**
```python
class UIManager:
    """Handles the on-screen display for the Channel Guide"""
    - show_channel_guide()
    - hide_channel_guide()
    - render_list_on_osd()
    - handle_guide_navigation()
```

---

## 🎮 Elegant Input Control Scheme

### **Keyboard Controls**
```
Navigation:
├── ← (Left Arrow)     → Previous video/restart current
├── → (Right Arrow)    → Next video (channel surf)
├── ↑ (Up Arrow)       → Volume up
├── ↓ (Down Arrow)     → Volume down
├── Space              → Play/Pause toggle
├── Backspace          → Restart current video
└── Hold ←/→           → Fast seek backward/forward

Special:
├── ESC                → Graceful shutdown
├── M                  → Mute toggle  
├── S                  → Mark as seen/unseen
├── I / P              → Show/Hide Channel Guide
```

### **Mouse Controls**
```
├── Left Click         → Play/Pause
├── Right Click        → Previous video/restart
├── Scroll Up          → Volume up
├── Scroll Down        → Volume down
├── Middle Click       → Next video (channel surf)
└── Hold Left/Right    → Fast seek
```

### **Resume Functionality**
```yaml
# Store resume positions in media_library.yml:
- FilePath: "Movies/Inception (2010).mkv"
  Title: "Inception"
  Status: "Unseen"
  ResumePosition: "00:45:12"
  LastWatched: "2023-10-27T10:00:00Z"

# Auto-resume if stopped >10% into content
# Clear resume position when marked as "Seen"
```

---

## 🧠 Smart Playback Logic

### **Playlist Compilation Algorithm**
```python
def compile_smart_playlist():
    """
    Elegant shuffling that respects series order
    """
    eligible_content = []
    
    # Add all unseen movies
    unseen_movies = get_unseen_movies()
    eligible_content.extend(unseen_movies)
    
    # Add next unseen episode per series
    for series in get_all_series():
        next_episode = get_next_unseen_episode(series)
        if next_episode:
            eligible_content.append(next_episode)
    
    return shuffle(eligible_content)
```

### **Playback Completion Detection**
```python
# Elegant completion detection methods:
1. mpv event listener (most reliable)
2. Playback position vs duration (95% threshold)
3. Time-based heuristic (watched >80% of runtime)
4. User manual marking
```

### **Resume Functionality**
```python
# Store resume positions in CSV:
FilePath,Title,Type,Status,ResumePosition,LastWatched
# Auto-resume if stopped >10% into content
# Clear resume position when marked as "Seen"
```

---

## 🎨 Visual Experience

### **Title Overlay System**
```python
class TitleOverlay:
    """Elegant on-screen information display"""
    - show_title_on_start(duration=3_seconds)
    - fade_in_out_animation()
    - minimal_typography()
    - optional_progress_indicator()
    - subtitle_status_indicator()
```

### **Visual Design Principles**
- **Minimal UI:** Content-first, interface-last
- **Smooth Transitions:** Fade effects between videos
- **Clean Typography:** Simple, readable overlay text
- **Dark Theme:** Reduce eye strain in low light

### **Channel Guide UI**
- **Activation:** Appears on `I` or `P` key press.
- **Layout:** A clean, vertical list of available titles.
- **Navigation:** Scroll with `↑`/`↓` keys, select with `Enter`.
- **Appearance:** Semi-transparent background overlay to maintain context of the currently playing video.
- **Auto-hide:** Fades out after a period of inactivity.

---

## 📁 File Structure & Organization

### **Project Structure**
```
pondtv/
├── src/
│   ├── boot_manager.py
│   ├── media_scanner.py  
│   ├── playlist_engine.py
│   ├── player_controller.py
│   ├── input_handler.py
│   ├── title_overlay.py
│   ├── ui_manager.py
│   └── utils/
│       ├── file_utils.py
│       ├── yaml_utils.py
│       └── logging_config.py
├── config/
│   ├── pondtv.service
│   ├── udev_rules/
│   └── mpv_config/
├── install/
│   └── setup.sh
└── logs/
```

### **USB Drive Structure (Auto-Generated)**
```
USB_DRIVE/
├── Movies/
├── TV_Shows/
├── media_library.yml          # Main database
├── .pondtv/
│   ├── seen_backup.yml        # Failsafe backup
│   ├── resume_positions.yml   # Resume data (or integrated into main lib)
│   └── last_scan.timestamp    # Optimization
└── .subtitles/                # Auto-detected subs
```

---

## 🛡️ Error Handling & Resilience

### **Failsafe Systems**
```python
# Robust error handling strategy:
1. USB Drive Missing → Show friendly message, wait for insertion
2. Corrupted YAML → Rebuild from file scan + restore seen status from backup
3. Media File Missing → Skip gracefully, log error, continue playlist
4. mpv Crash → Restart player, resume from last position
5. System Resources → Monitor memory/CPU, optimize playback quality
```

### **Backup Strategy**
- **Seen Status:** Daily backup to `.pondtv/seen_backup.yml`
- **Resume Positions:** Real-time updates to prevent loss
- **Database Recovery:** Auto-rebuild with status preservation

---

## ⚡ Performance Optimizations

### **Fast Boot Targets**
- **Total Boot Time:** <15 seconds (power on to first video)
- **USB Detection:** <3 seconds
- **Database Load:** <2 seconds for 1000+ files
- **First Video Start:** <5 seconds

### **Memory Management**
- **CSV Caching:** Load once, update incrementally
- **mpv Configuration:** Optimize for Pi 4 hardware
- **Background Scanning:** Non-blocking media discovery

---

## 🎯 Implementation Priority

### **MVP Features (Must Have)**
1. ✅ USB auto-detection and mounting
2. ✅ Basic media scanning (movies + TV shows)
3. ✅ Basic YAML database generation
4. ✅ Smart playlist compilation
5. ✅ mpv playback integration
6. ✅ Basic keyboard controls

### **Enhanced Features (Should Have)**
1. Resume functionality
2. Title overlay display
3. Mouse input support
4. Subtitle auto-detection
5. Playback completion detection
6. Channel Guide UI

### **Future Features (Could Have)**
1. Web interface for library management
2. Multiple USB drive support
3. Genre-based filtering
4. Visual filters and effects

