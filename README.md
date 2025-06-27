# 🌊 PondTV

<p align="left">
  <img src="assets/logo.png" alt="PondTV Logo" width="256"/>
</p>

> A calm, offline alternative to streaming services—content flows from your personal collection, not an endless stream.

PondTV turns your Raspberry Pi into a plug-and-play TV channel for your media. Think of it as a dumb-TV, just like dumb-phones: no apps, no menus, just simple playback from your USB drive. Power on and watch—effortless.

This project is designed for a dedicated, offline media player experience on a Raspberry Pi connected to a TV.

## ✨ Features

- **Instant-On Playback** - Boots straight into fullscreen media playback.
- **Smart Playlists** - Prevents binge-watching with intelligent episode selection. Automatically filters out watched content and prioritizes the next unseen episode in a series.
- **Channel Surfing** - Simple, intuitive controls to switch content.
- **Offline First** - No internet connection required. All content and metadata are stored locally on your USB drive.
- **Content Tracking & Resumption** - Remembers your progress in any video and tracks which content you've seen.
- **Hot-Plug & Reconnect** - Seamlessly handles USB drive disconnections and reconnects during operation.

## 🗂️ Preparing Your Media

To use PondTV, you need to organize your movie and TV show files on a USB drive.

1.  **Format your drive:** Use a standard format like `exFAT` or `NTFS`.
2.  **Organize your folders:** Create `Movies` and `TV_Shows` directories at the root of the drive. The structure should look like this:

    ```
    USB_DRIVE/
    ├── Movies/
    │   └── Movie Title (Year).mkv
    └── TV_Shows/
        └── ShowName/
            └── Season 01/
                └── ShowName - S01E01 - Episode.mp4
    ```
3.  **Use the example:** For a working example, check out the `example_media_drive` folder included in this repository. You can copy its structure to your own USB drive.

When you first run PondTV, it will scan this drive and create a `media_library.yml` and a `config.yml` file to manage your content.

## 🚀 Effortless Installation

PondTV is designed to be installed without needing a keyboard or command line attached to the Raspberry Pi.

1.  **Download the latest release:** Go to the [Pond Releases Page](https://github.com/kdklv/pond/releases) and download the `pondtv-payload.zip` file.
2.  **Flash Raspberry Pi OS:** Use the Raspberry Pi Imager to flash a fresh, clean **Raspberry Pi OS Lite (64-bit)** image to your SD card.
    - Before writing, use the settings to pre-configure your username and enable SSH if you wish.
3.  **Copy the Payload:** Unzip the `pondtv-payload.zip` file. Copy all of its contents (e.g., the `pip_packages` folder, the `user-data` file, etc.) to the `boot` partition of the SD card you just flashed.
4.  **First Boot:**
    - Connect your Raspberry Pi to the **internet via an Ethernet cable** just for this first boot. This is required to download the `mpv` media player.
    - Eject the SD card, insert it into your Pi, and power it on.

The Pi will boot up, install everything automatically, and then reboot one last time. After that, PondTV is fully installed and will start on boot. You can now disconnect the internet cable and use it completely offline.

Just plug in your USB media drive and enjoy your personal TV channel.

<details>
<summary>Alternative Installation (for advanced users via SSH)</summary>

If you are comfortable with the command line, you can install PondTV by cloning the repository directly onto your Raspberry Pi.

1.  **SSH into your Raspberry Pi.**
2.  **Clone the repository:**
    ```bash
    git clone https://github.com/kdklv/pond.git
    cd pond
    ```
3.  **Run the installation script:**
    This script will install all dependencies, copy the application files to `/opt/pondtv`, and set up the systemd service.
    ```bash
    chmod +x dist/install_ssh.sh
    sudo dist/install_ssh.sh
    ```
</details>

## 🎮 Controls

- **Space** - Play/Pause
- **Right Arrow** - Next video
- **Left Arrow** - Previous video
- **Backspace** - Restart current video
- **Up Arrow** - Volume up
- **Down Arrow** - Volume down
- **M** - Toggle mute
- **S** - Mark current video as seen (skips to next unseen content)
- **I / P** - Toggle channel guide
- **Escape** - Quit

## 🛠️ Configuration

PondTV creates a `config.yml` on your USB drive for customization. You can edit this file to change player and UI behavior. See the default values in `config/pondtv.service` for reference.

## 📅 Future Ideas

- **Commercial Breaks** - Insert commercials between movies for a nostalgic TV feel
- **Random Mode** - Shuffle content randomly, mimicking flipping through TV channels
- **Web Interface** - Manage your library through a browser
- **Multiple USB Support** - Handle content from several drives
- **Visual Effects** - Add filters and effects to playback
- **Flashable OS Image** - Simplify setup by creating a complete, flashable Raspberry Pi OS image with PondTV pre-installed. A user could simply flash the image to an SD card, plug in their media drive, and have it work instantly.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

**PondTV** — Your personal, offline TV channel. Simple, like still water. 