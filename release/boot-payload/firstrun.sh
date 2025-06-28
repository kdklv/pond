#!/bin/bash

# PondTV Auto-Installer for Raspberry Pi OS
# This script runs automatically on first boot when placed in the boot partition

set -e

# Log everything
exec > >(tee -a /var/log/pondtv-install.log)
exec 2>&1

echo "🌊 PondTV Auto-Installer Starting..."
echo "===================================="
date

# Wait for network connectivity
echo "⏳ Waiting for network connectivity..."
for i in {1..30}; do
    if ping -c 1 github.com &> /dev/null; then
        echo "✅ Network is ready"
        break
    fi
    echo "   Attempt $i/30..."
    sleep 2
done

# Install dependencies
echo "📦 Installing system dependencies..."
apt-get update -qq
apt-get install -y mpv python3-pip git

# Download and install PondTV
echo "📥 Downloading PondTV..."
cd /tmp
rm -rf pond
git clone https://github.com/kdklv/pond.git
cd pond

echo "🐍 Installing Python dependencies..."
pip3 install -r requirements.txt

echo "📁 Installing PondTV to /opt/pondtv..."
mkdir -p /opt/pondtv
cp -r ./pondtv /opt/pondtv/
cp ./run.py /opt/pondtv/
cp ./requirements.txt /opt/pondtv/
chown -R pi:pi /opt/pondtv

# Create systemd service
echo "⚙️  Creating systemd service..."
cat > /etc/systemd/system/pondtv.service << 'EOF'
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
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
EOF

# Enable the service
echo "🚀 Enabling PondTV service..."
systemctl daemon-reload
systemctl enable pondtv.service

# Cleanup
cd /
rm -rf /tmp/pond

echo ""
echo "✅ PondTV Installation Complete!"
echo "🔄 System will reboot in 10 seconds..."
echo "🎬 After reboot, plug in your USB drive and enjoy!"
echo ""

# Remove this script so it doesn't run again
rm -f /boot/firstrun.sh

# Schedule a reboot
sleep 10
reboot 