#!/bin/bash
# This script builds the user payload for the first-boot installation.
set -e

DIST_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$DIST_DIR")"
PAYLOAD_DIR="$DIST_DIR/payload"

echo "--- Creating PondTV Installation Payload ---"

# 1. Clean and create payload directory
rm -rf "$PAYLOAD_DIR"
mkdir -p "$PAYLOAD_DIR/pip_packages"

# 2. Download Python dependencies as wheels
echo "--> Downloading Python wheels for offline installation..."
python3 -m pip download -r "$PROJECT_ROOT/requirements.txt" -d "$PAYLOAD_DIR/pip_packages"

# 3. Copy application files
echo "--> Copying application files..."
mkdir "$PAYLOAD_DIR/pondtv"
cp -r "$PROJECT_ROOT/src/pondtv" "$PAYLOAD_DIR/pondtv/app"
cp "$PROJECT_ROOT/src/run.py" "$PAYLOAD_DIR/pondtv/"
cp "$PROJECT_ROOT/requirements.txt" "$PAYLOAD_DIR/pondtv/"
cp "$PROJECT_ROOT/config/pondtv.service" "$PAYLOAD_DIR/"

# 4. Create the first-boot script (for cloud-init)
echo "--> Creating first-boot script (user-data)..."
cat > "$PAYLOAD_DIR/user-data" <<EOF
#cloud-config
# PondTV First-Boot Setup
# This will run on the first boot to install PondTV.
# NOTE: An internet connection is required ONCE to install 'mpv'.

packages:
  - mpv

runcmd:
  - 'echo "--- Installing PondTV ---"'
  - 'pip3 install --no-index --find-links=/boot/pip_packages -r /boot/pondtv/requirements.txt'
  - 'mkdir -p /opt/pondtv'
  - 'cp -r /boot/pondtv/* /opt/pondtv/'
  - 'sed -i "s|/opt/pondtv/run.py|/opt/pondtv/run.py|g" /boot/pondtv.service'
  - 'cp /boot/pondtv.service /etc/systemd/system/'
  - 'systemctl daemon-reload'
  - 'systemctl enable pondtv.service'
  - 'echo "PondTV installation complete. Rebooting in 10 seconds..."'
  - 'sleep 10'
  - 'reboot'
EOF

# 5. Create a simple README for the user inside the payload
echo "--> Creating user instructions..."
cat > "$PAYLOAD_DIR/INSTRUCTIONS.txt" <<EOF
PondTV Simple Setup
===================

To install PondTV on your Raspberry Pi:

1. Flash a fresh Raspberry Pi OS Lite (64-bit) image to your SD card using Raspberry Pi Imager.
   (In the imager settings, it's a good idea to set a hostname and enable SSH).

2. Copy all the files from this 'payload' directory to the 'boot' partition of the SD card.

3. The Raspberry Pi MUST be connected to the internet for the first boot to download 'mpv'.

4. Eject the SD card, put it in your Raspberry Pi, and power it on.

The Pi will boot, install everything automatically, and then reboot. After this, the internet is no longer required.
EOF

chmod +x "$PAYLOAD_DIR/user-data"

echo "--- Payload created successfully in 'dist/payload' ---"
echo "Zip this 'payload' folder for distribution." 