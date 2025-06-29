#!/bin/bash
set -e

# PondTV One-Command Installer
# Usage: curl -sSL https://raw.githubusercontent.com/kdklv/pond/main/scripts/install_one_command.sh | sudo bash

echo "🌊 PondTV One-Command Installer"
echo "================================"

# Check for root privileges
if [ "$EUID" -ne 0 ]; then
  echo "❌ This script must be run as root. Please use:"
  echo "   curl -sSL https://raw.githubusercontent.com/kdklv/pond/main/scripts/install_one_command.sh | sudo bash"
  exit 1
fi

# Check if we're on Raspberry Pi OS
if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
  echo "⚠️  Warning: This script is designed for Raspberry Pi OS"
fi

echo "📦 Installing system dependencies..."
apt-get update -qq
apt-get install -y mpv python3-pip git python3-venv

echo "📥 Downloading PondTV..."
cd /tmp
rm -rf pond
git clone https://github.com/kdklv/pond.git
cd pond

APP_DIR="/opt/pondtv"
VENV_DIR="$APP_DIR/venv"

echo "🐍 Installing Python dependencies into a virtual environment..."
mkdir -p $APP_DIR
chown pi:pi $APP_DIR
sudo -u pi python3 -m venv $VENV_DIR
sudo -u pi $VENV_DIR/bin/pip install -r requirements.txt

echo "📁 Installing PondTV to $APP_DIR..."
cp -r ./pondtv $APP_DIR/
cp ./run.py $APP_DIR/
cp ./requirements.txt $APP_DIR/ # For reference

echo "⚙️  Creating systemd service..."
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
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
EOF

echo "🚀 Enabling PondTV service..."
systemctl daemon-reload
systemctl enable pondtv.service

echo ""
echo "✅ PondTV Installation Complete!"
echo ""
echo "🎬 Next steps:"
echo "   1. Plug in your USB drive with movies/TV shows"
echo "   2. Reboot your Pi: sudo reboot"
echo "   3. PondTV will start automatically and scan your media"
echo ""
echo "📚 Useful commands:"
echo "   • Check status: sudo systemctl status pondtv"
echo "   • View logs: sudo journalctl -u pondtv -f"
echo "   • Restart: sudo systemctl restart pondtv"
echo ""

# Cleanup
cd /
rm -rf /tmp/pond 