# 🌊 PondTV

<p align="left">
  <img src="logo.png" alt="PondTV Logo" width="200"/>
</p>

> A calm, offline alternative to streaming services—content flows from your personal collection, not an endless stream.

PondTV turns your Raspberry Pi into a plug-and-play TV channel for your media. Think of it as a dumb-TV, just like dumb-phones: no apps, no menus, just simple playback from your USB drive. Power on and watch—effortless.

## ✨ Features

- **Instant-On Playback** - Boots straight into fullscreen media
- **Smart Playlists** - Prevents binge-watching with intelligent episode selection  
- **Channel Surfing** - Easy controls to switch content
- **Offline Operation** - No internet needed, all content is local
- **Resume Playback** - Pick up where you left off
- **Auto-Discovery** - Scans and catalogs your media

## 🚀 Quick Start

### Hardware Requirements
- Raspberry Pi 4 (or 3B+ minimum)
- USB drive with your media collection
- HDMI display

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/pond_tv.git
   cd pond_tv
   ```

2. **Run the installation script:**
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

3. **Organize your media on USB drive:**
   ```
   USB_DRIVE/
   ├── Movies/
   │   └── Movie Title (Year).mkv
   └── TV_Shows/
       └── ShowName/
           └── Season 01/
               └── ShowName - S01E01 - Episode.mp4
   ```
   (We're sure your library of digitized VHS tapes and *entirely legal* media will look great here.)

4. **Start PondTV:**
   ```bash
   python run_pondtv.py
   ```

## 🎮 Controls

- **Space** - Play/Pause
- **Right Arrow** - Next video
- **Left Arrow** - Restart current video
- **S** - Mark as seen
- **G** - Toggle channel guide
- **Q** - Quit

## 🛠️ Configuration

PondTV creates a `config.yml` on your USB drive for customization:

```yaml
ui:
  title_display_duration: 3
  channel_guide_items_per_page: 10

playback:
  seen_threshold_percentage: 95
  auto_mark_seen: true
```

## 📋 Requirements

- Python 3.7+
- mpv media player
- Dependencies listed in `pondtv/requirements.txt`

## 📅 Future Ideas

Here are some potential enhancements for PondTV in the future:

- **Commercial Breaks** - Insert commercials between movies for a nostalgic TV feel
- **Random Mode** - Shuffle content randomly, mimicking flipping through TV channels
- **Web Interface** - Manage your library through a browser
- **Multiple USB Support** - Handle content from several drives
- **Visual Effects** - Add filters and effects to playback


## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the [MIT License](LICENSE).


---

**PondTV** — Your personal, offline TV channel. Simple, like still water. 