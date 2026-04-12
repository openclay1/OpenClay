#!/bin/bash
# build_mac_app.sh — Package OpenClay as macOS .app
# Run from the Open Clay directory: ./build_mac_app.sh
set -e

echo "Building OpenClay.app..."

# Ensure dependencies
pip install pyinstaller pillow 2>/dev/null

# Generate icon if missing
python3 openclay_icon.py 2>/dev/null || true

# Build with PyInstaller
pyinstaller --onedir --windowed \
  --icon=openclay.icns \
  --name="OpenClay" \
  --add-data "SOUL.md:." \
  --add-data "BRAIN.md:." \
  --add-data "AGENTS.md:." \
  --add-data "lang_detect.py:." \
  --add-data "daily_agents.py:." \
  --add-data "predict_engine.py:." \
  --add-data "vibe_brain.py:." \
  --add-data "model_config.py:." \
  --add-data "voice_input.py:." \
  --add-data "audit_log.py:." \
  --add-data "first_screen.py:." \
  --add-data "integration_detector.py:." \
  openclay_app.py

# Install to ~/Applications
mkdir -p ~/Applications
cp -r dist/OpenClay.app ~/Applications/
echo "Installed to ~/Applications/OpenClay.app"

# Offer to add to Dock
read -p "Agregar OpenClay al Dock? / Add to Dock? [y/N] " yn
if [[ "$yn" =~ ^[Yy]$ ]]; then
  defaults write com.apple.dock persistent-apps -array-add \
    "<dict><key>tile-data</key><dict><key>file-data</key><dict>\
    <key>_CFURLString</key><string>$HOME/Applications/OpenClay.app</string>\
    <key>_CFURLStringType</key><integer>0</integer>\
    </dict></dict></dict>"
  killall Dock
  echo "Added to Dock."
fi

echo "Done. / Listo."
