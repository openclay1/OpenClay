#!/bin/bash
# build_dmg.sh — Create OpenClay.dmg installer for macOS
# Requires build_mac_app.sh to be run first
set -e

APP_NAME="OpenClay"
DMG_NAME="${APP_NAME}.dmg"
VOL_NAME="${APP_NAME} Installer"
APP_PATH="dist/${APP_NAME}.app"
DMG_TEMP="dist/${APP_NAME}_temp.dmg"

echo "Creating ${DMG_NAME}..."

# Verify .app exists
if [ ! -d "$APP_PATH" ]; then
  echo "Error: $APP_PATH not found. Run build_mac_app.sh first."
  exit 1
fi

# Create temporary DMG
hdiutil create -size 200m -volname "$VOL_NAME" -srcfolder "$APP_PATH" \
  -ov -format UDRW "$DMG_TEMP"

# Mount and customize
MOUNT_DIR=$(hdiutil attach "$DMG_TEMP" | grep "Volumes" | awk '{print $3}')

# Create Applications symlink for drag-to-install
ln -sf /Applications "$MOUNT_DIR/Applications"

# Set window layout
# Arrastra OpenClay a Aplicaciones / Drag OpenClay to Applications
echo '
tell application "Finder"
  tell disk "'"$VOL_NAME"'"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set bounds of container window to {100, 100, 640, 400}
    set viewOptions to the icon view options of container window
    set arrangement of viewOptions to not arranged
    set icon size of viewOptions to 128
    set position of item "'"$APP_NAME.app"'" of container window to {140, 150}
    set position of item "Applications" of container window to {400, 150}
    close
    open
  end tell
end tell
' | osascript 2>/dev/null || true

# Unmount
hdiutil detach "$MOUNT_DIR"

# Convert to compressed DMG
hdiutil convert "$DMG_TEMP" -format UDZO -imagekey zlib-level=9 \
  -o "dist/${DMG_NAME}"
rm -f "$DMG_TEMP"

echo "Created dist/${DMG_NAME}"
echo "Arrastra OpenClay a Aplicaciones / Drag OpenClay to Applications"
