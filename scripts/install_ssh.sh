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
apt-get install -y mpv python3-pip python3-venv

# 3. Create application directory and virtual environment
APP_DIR="/opt/pondtv"
VENV_DIR="$APP_DIR/venv"
echo "--> Creating application directory and virtual environment at $APP_DIR..."
mkdir -p $APP_DIR
chown pi:pi $APP_DIR
sudo -u pi python3 -m venv $VENV_DIR

# 4. Install Python libraries into the virtual environment
echo "--> Installing Python libraries..."
sudo -u pi $VENV_DIR/bin/pip install -r requirements.txt

# 5. Copy application files
echo "--> Copying application files to $APP_DIR..."
# Copy the application
cp -r ./pondtv $APP_DIR/
cp ./run.py $APP_DIR/
cp ./requirements.txt $APP_DIR/ # Copying requirements for reference

# 6. Create and install the systemd service
echo "--> Creating systemd service..."
cat > /etc/systemd/system/pondtv.service << EOF
[Unit]
Description=PondTV Media Player
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=$APP_DIR
ExecStart=$VENV_DIR/bin/python3 $APP_DIR/run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 7. Enable and start the service
echo "--> Enabling and starting the PondTV service..."
systemctl daemon-reload
systemctl enable pondtv.service

echo "--- PondTV Installation Complete! ---"
echo "PondTV will start automatically on next boot."
echo "To start now: sudo systemctl start pondtv.service"
echo "Check status with: sudo systemctl status pondtv.service"
echo "View logs with: sudo journalctl -u pondtv.service -f" 