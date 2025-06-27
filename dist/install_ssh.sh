#!/bin/bash
# This script installs PondTV for users who have cloned the repo via SSH.
set -e

echo "--- Starting PondTV SSH Installation ---"

# 1. Check for root privileges
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root using 'sudo ./install_ssh.sh'"
  exit 1
fi

# 2. Find project root (the directory containing 'dist' and 'src')
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "Project root found at: $PROJECT_ROOT"

# 3. Update package list and install system dependencies
echo "--> Installing system dependencies (mpv, python3-pip)..."
apt-get update
apt-get install -y mpv python3-pip

# 4. Install Python libraries
echo "--> Installing Python libraries from requirements.txt..."
pip3 install -r "$PROJECT_ROOT/requirements.txt"

# 5. Copy application files to /opt/pondtv
APP_DIR="/opt/pondtv"
echo "--> Copying application files to $APP_DIR..."
mkdir -p "$APP_DIR"
cp -r "$PROJECT_ROOT/src/"* "$APP_DIR/"
chown -R pi:pi "$APP_DIR"

# 6. Install the systemd service
SERVICE_FILE="$PROJECT_ROOT/config/pondtv.service"
SERVICE_DEST="/etc/systemd/system/pondtv.service"
echo "--> Installing systemd service..."
cp "$SERVICE_FILE" "$SERVICE_DEST"

# 7. Enable and start the service
echo "--> Enabling and starting the PondTV service..."
systemctl daemon-reload
systemctl enable pondtv.service
systemctl start pondtv.service

echo "--- PondTV Installation Complete! ---"
echo "The PondTV service is now running."
echo "Check its status with: sudo systemctl status pondtv.service"
echo "Logs can be viewed with: sudo journalctl -u pondtv.service -f" 