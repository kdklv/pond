# 🪷 PondTV ⛲


<p align="left">
  <img src="logo.png" alt="PondTV Logo" width="256"/>
</p>

> A calm, offline alternative to streaming services—content flows from your personal collection. Just power on and watch.

PondTV turns your Raspberry Pi into a plug-and-play TV channel for your media. Think of it as a dumb-TV, just like dumb-phones: no apps, no menus, just simple playback from your USB drive. 

## 🐸 Features

- **Instant-On Playback** - Boots straight into fullscreen media
- **Smart Playlists** - Prevents binge-watching by intelligently selecting the next episode in a series
- **Channel Surfing** - Simple controls to switch content
- **Offline First** - No internet required after setup
- **Content Tracking** - Remembers what you've watched and where you left off
- **Robust USB Handling** - Reliably detects and mounts USB drives on-the-fly

## 🌿 Preparing Your Media

Organize your files on a USB drive like this:

```
USB_DRIVE/
├── Movies/
│   └── Movie Title (Year).mkv
└── TV_Shows/
    └── ShowName/
        └── Season 01/
            └── ShowName - S01E01 - Episode.mp4
```

See the `examples/` folder for a working example you can copy.

## 🍀 Installation

The recommended installation method is to use the command below, which will download and run the installer automatically. This works for a fresh Raspberry Pi OS installation with SSH enabled.

```bash
curl -sSL https://raw.githubusercontent.com/kdklv/pond/main/scripts/install.sh | sudo bash
```

For headless setup without a keyboard or monitor attached, you can pre-configure the Raspberry Pi OS with WiFi and place the installer script on the boot partition to have it run automatically on first boot. Please refer to the Raspberry Pi documentation for details on headless setup.

## 🌀 Controls

| Key | Action |
|-----|--------|
| **Space** | Play/Pause |
| **→** | Next video |
| **←** | Previous video |
| **↑/↓** | Volume up/down |
| **Backspace** | Restart current video |
| **M** | Toggle mute |
| **S** | Mark as seen (skip to next) |
| **I/P** | Toggle guide |
| **Esc** | Quit |

## 🏊 Configuration

PondTV creates a `config.yml` on your USB drive for customization. The app will generate default settings on first run.

## 🏝 Future Ideas

- **Random Mode** - Shuffle content randomly, mimicking flipping through TV channels
- **Commercial Breaks** - Insert commercials between content for nostalgic TV feel
- **Visual Effects** - Add filters and effects to playback 
- **Flashable OS Image** - Complete SD card image with PondTV pre-installed
- **Web Interface** - Manage your library through a browser
- **Multiple USB Support** - Handle content from several drives

## 🤝 Contributing

Contributions welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

**PondTV** — Your personal, offline TV channel. Simple, like still water. 
