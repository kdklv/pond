#!/bin/bash
set -e

echo "--- Starting PondTV Installation ---"

# 1. Check for root privileges
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root using 'sudo ./install.sh'"
  exit
fi

# 2. Update package list and install dependencies
echo "--> Updating package list and installing dependencies (mpv, python3-pip)..."
apt-get update
apt-get install -y mpv python3-pip

# 3. Install Python libraries
echo "--> Installing Python libraries from requirements.txt..."
pip3 install -r pondtv/requirements.txt

# 4. Copy application files
APP_DIR="/home/pi/pondtv"
echo "--> Copying application files to $APP_DIR..."
mkdir -p $APP_DIR
cp -r ./* $APP_DIR/

# Ensure correct ownership
chown -R pi:pi $APP_DIR

# 5. Install the systemd service
SERVICE_FILE="pondtv/config/pondtv.service"
SERVICE_DEST="/etc/systemd/system/pondtv.service"
echo "--> Installing systemd service from $SERVICE_FILE..."
cp $APP_DIR/$SERVICE_FILE $SERVICE_DEST

# 6. Enable and start the service
echo "--> Enabling and starting the PondTV service..."
systemctl daemon-reload
systemctl enable pondtv.service
systemctl start pondtv.service

echo "--- PondTV Installation Complete! ---"
echo "The PondTV service is now running."
echo "Check its status with: sudo systemctl status pondtv.service"
echo "Logs can be viewed with: sudo journalctl -u pondtv.service -f" 