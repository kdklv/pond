#!/bin/bash
set -e

# PondTV Universal Installer
# This script handles both local and remote installation.

echo "🌊 PondTV Installer"
echo "===================="

# --- Root Check ---
if [ "$EUID" -ne 0 ]; then
  echo "❌ This script must be run as root."
  exit 1
fi

# Determine user to run the service as
PI_USER=${SUDO_USER:-pi}
echo "ℹ️  Installing for user: $PI_USER"

# --- System Setup ---
echo "📦 Installing system dependencies..."
apt-get update -qq
apt-get install -y mpv python3-pip git python3-venv libmpv-dev udisks2 python3-gi gir1.2-glib-2.0 gir1.2-udisks-2.0

# --- App Setup ---
APP_DIR="/opt/pondtv"
VENV_DIR="$APP_DIR/venv"
GIT_REPO_URL="https://github.com/kdklv/pond.git"
TEMP_DIR="/tmp/pond"

# --- Installation ---
echo "📥 Cloning or copying PondTV source..."
# If running from a local git repo, copy files instead of cloning
if [ -d ".git" ]; then
    echo "   (Local repository detected, copying files...)"
    mkdir -p $TEMP_DIR
    rsync -a --exclude='.git' ./ $TEMP_DIR/
else
    echo "   (Cloning from GitHub...)"
    rm -rf $TEMP_DIR
    git clone $GIT_REPO_URL $TEMP_DIR
fi

cd $TEMP_DIR

echo "🐍 Creating virtual environment and installing Python dependencies..."
# Clean up old venv if it exists, to ensure a clean state
rm -rf $VENV_DIR
mkdir -p $APP_DIR
chown $PI_USER:$PI_USER $APP_DIR
# Create venv with access to system packages (for PyGObject)
sudo -u $PI_USER python3 -m venv --system-site-packages $VENV_DIR
sudo -u $PI_USER $VENV_DIR/bin/pip install -r requirements.txt

echo "📁 Installing PondTV to $APP_DIR..."
# Copy the application logic
cp -r ./pondtv $APP_DIR/
# Copy the requirements for reference
cp ./requirements.txt $APP_DIR/

# --- Permissions and Services ---
echo "⚙️  Configuring permissions and systemd service..."

# Remove old pkla rule if it exists
rm -f /etc/polkit-1/localauthority/50-local.d/60-pondtv-mount-policy.pkla

# Install polkit rule for allowing mounting
POLKIT_RULES_DIR="/etc/polkit-1/rules.d"
mkdir -p $POLKIT_RULES_DIR
cp ./release/40-pondtv-udisks.rules "$POLKIT_RULES_DIR/"
systemctl restart polkit
systemctl restart udisks2.service

# Create and install the systemd service
cat > /etc/systemd/system/pondtv.service << EOF
[Unit]
Description=PondTV Media Player
After=network.target polkit.service udisks2.service
Wants=polkit.service udisks2.service

[Service]
Type=simple
User=$PI_USER
WorkingDirectory=$APP_DIR
ExecStartPre=/bin/sleep 10
ExecStart=$VENV_DIR/bin/python3 -m pondtv.main
Restart=always
RestartSec=10
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
EOF

echo "🚀 Enabling PondTV service..."
systemctl daemon-reload
systemctl enable pondtv.service

# --- Cleanup ---
echo "🧹 Cleaning up temporary files..."
rm -rf $TEMP_DIR

# --- Done ---
echo ""
echo "✅ PondTV Installation Complete!"
echo ""
echo "🎬 Next steps:"
echo "   1. Plug in your USB drive with media."
echo "   2. Reboot your Pi with 'sudo reboot'."
echo ""
echo "📚 Useful commands:"
echo "   - Check status: sudo systemctl status pondtv"
echo "   - View logs:   sudo journalctl -u pondtv -f"
echo "   - Restart:     sudo systemctl restart pondtv"
echo "" 