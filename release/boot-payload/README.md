# PondTV Boot Payload

This directory contains files for automatic PondTV installation on Raspberry Pi OS.

## How to Use

1. **Flash Raspberry Pi OS Lite** to your SD card using Raspberry Pi Imager
   - Choose "Raspberry Pi OS Lite (64-bit)" 
   - Before writing, click the gear icon to configure:
     - Enable SSH (optional, for troubleshooting)
     - Set username and password
     - Configure Wi-Fi credentials (required for installation)

2. **Copy the payload** to the boot partition:
   - After flashing, the SD card will have a `boot` partition visible on your computer
   - Copy `firstrun.sh` to the root of the boot partition
   - Make sure it's named exactly `firstrun.sh`

3. **First boot**:
   - Insert the SD card into your Pi and power on
   - The Pi will connect via Wi-Fi and install automatically
   - The installation will happen automatically and the Pi will reboot when done

4. **After installation**:
   - Plug in your USB drive with movies/TV shows
   - PondTV will start automatically and scan your media

## What happens during installation

The `firstrun.sh` script will:
- Wait for network connectivity
- Install system dependencies (mpv, python3-pip, git)
- Download PondTV from GitHub
- Install Python dependencies
- Set up PondTV as a system service
- Reboot the system

## Troubleshooting

- Check installation logs: `sudo journalctl -u firstrun`
- Check PondTV logs: `sudo journalctl -u pondtv -f`
- Manual start: `sudo systemctl start pondtv` 