#!/bin/bash
set -e

echo "--- Starting PondTV Installation ---"

# 1. Check for root privileges
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root using 'sudo ./scripts/install_ssh.sh'"
  exit 1
fi

# 2. Update package list and install dependencies
echo "--> Updating package list and installing dependencies..."
apt-get update
apt-get install -y mpv python3-pip

# 3. Install Python libraries
echo "--> Installing Python libraries..."
pip3 install -r requirements.txt

# 4. Copy application files
APP_DIR="/opt/pondtv"
echo "--> Copying application files to $APP_DIR..."
mkdir -p $APP_DIR

# Copy the application
cp -r ./pondtv $APP_DIR/
cp ./run.py $APP_DIR/
cp ./requirements.txt $APP_DIR/

# Ensure correct ownership
chown -R pi:pi $APP_DIR

# 5. Create and install the systemd service
echo "--> Creating systemd service..."
cat > /etc/systemd/system/pondtv.service << EOF
[Unit]
Description=PondTV Media Player
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/pondtv
ExecStart=/usr/bin/python3 /opt/pondtv/run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 6. Enable and start the service
echo "--> Enabling and starting the PondTV service..."
systemctl daemon-reload
systemctl enable pondtv.service

echo "--- PondTV Installation Complete! ---"
echo "PondTV will start automatically on next boot."
echo "To start now: sudo systemctl start pondtv.service"
echo "Check status with: sudo systemctl status pondtv.service"
echo "View logs with: sudo journalctl -u pondtv.service -f" 