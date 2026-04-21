#!/usr/bin/env bash
# create_app.sh — Build OpenClay.app for macOS
# Run once from the project root: bash create_app.sh
# Idempotent: safe to run multiple times — overwrites cleanly.
#
# What this does:
#   1. Compiles OpenClay.applescript into a stay-open applet
#   2. Bakes PROJECT_DIR into launcher.sh and bundles it inside the .app
#   3. Writes a custom Info.plist (name, icon, stay-open, bundle ID)
#   4. Copies the icon (uses openclay.icns if present, generates from PNG otherwise)
#   5. Verifies the bundle structure and syntax-checks launcher.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="OpenClay"
APP_PATH="$SCRIPT_DIR/$APP_NAME.app"
CONTENTS="$APP_PATH/Contents"
MACOS_DIR="$CONTENTS/MacOS"
RESOURCES_DIR="$CONTENTS/Resources"
TMP_APP="/tmp/openclay_build_$$.app"

echo ""
echo "  Building $APP_NAME.app"
echo "  Project root: $SCRIPT_DIR"
echo ""

# ── 1. Clean previous build ───────────────────────────────────────
rm -rf "$APP_PATH" "$TMP_APP"

# ── 2. Compile the AppleScript into an applet ─────────────────────
if [ ! -f "$SCRIPT_DIR/OpenClay.applescript" ]; then
    echo "  ERROR: OpenClay.applescript not found in $SCRIPT_DIR" >&2
    exit 1
fi

echo "  Compiling OpenClay.applescript..."
osacompile -o "$TMP_APP" "$SCRIPT_DIR/OpenClay.applescript"

# ── 3. Assemble the bundle from the compiled applet ───────────────
# Move the osacompile output to the final path, then post-process.
mv "$TMP_APP" "$APP_PATH"

# osacompile names the binary "applet" — rename it to match CFBundleExecutable.
if [ -f "$MACOS_DIR/applet" ]; then
    mv "$MACOS_DIR/applet" "$MACOS_DIR/$APP_NAME"
fi
chmod +x "$MACOS_DIR/$APP_NAME"

# ── 4. Write custom Info.plist ────────────────────────────────────
cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>OpenClay</string>
    <key>CFBundleDisplayName</key>
    <string>OpenClay</string>
    <key>CFBundleIdentifier</key>
    <string>ai.coana.openclay</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleExecutable</key>
    <string>${APP_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>openclay</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>LSMinimumSystemVersion</key>
    <string>11.0</string>
    <key>LSUIElement</key>
    <false/>
    <key>NSAppleScriptEnabled</key>
    <true/>
    <key>OSAAppletStayOpen</key>
    <true/>
    <key>NSHumanReadableCopyright</key>
    <string>COANA Labs · San Juan, Puerto Rico</string>
</dict>
</plist>
PLIST

# ── 5. Bundle launcher.sh with PROJECT_DIR baked in ───────────────
if [ ! -f "$SCRIPT_DIR/launcher.sh" ]; then
    echo "  ERROR: launcher.sh not found in $SCRIPT_DIR" >&2
    exit 1
fi

mkdir -p "$RESOURCES_DIR"
# Replace the __PROJECT_DIR__ placeholder with the actual path
sed "s|__PROJECT_DIR__|$SCRIPT_DIR|g" "$SCRIPT_DIR/launcher.sh" \
    > "$RESOURCES_DIR/launcher.sh"
chmod +x "$RESOURCES_DIR/launcher.sh"

# Syntax-check the bundled launcher before finishing
if ! bash -n "$RESOURCES_DIR/launcher.sh"; then
    echo "  ERROR: launcher.sh has syntax errors — build aborted." >&2
    exit 1
fi
echo "  launcher.sh syntax: OK"

# ── 6. Copy icon ──────────────────────────────────────────────────
if [ -f "$SCRIPT_DIR/openclay.icns" ]; then
    cp "$SCRIPT_DIR/openclay.icns" "$RESOURCES_DIR/openclay.icns"
    echo "  Icon: copied openclay.icns"
elif [ -f "$SCRIPT_DIR/openclay_512.png" ]; then
    echo "  Icon: generating .icns from openclay_512.png..."
    ICONSET_DIR="/tmp/openclay_$$.iconset"
    mkdir -p "$ICONSET_DIR"
    for size in 16 32 64 128 256 512; do
        sips -z $size $size "$SCRIPT_DIR/openclay_512.png" \
            --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
        sips -z $((size*2)) $((size*2)) "$SCRIPT_DIR/openclay_512.png" \
            --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
    done
    iconutil -c icns "$ICONSET_DIR" -o "$RESOURCES_DIR/openclay.icns"
    rm -rf "$ICONSET_DIR"
    echo "  Icon: openclay.icns generated"
else
    echo "  Icon: none found — using default applet icon"
fi

# ── 7. Verify bundle structure ────────────────────────────────────
echo ""
echo "  Bundle contents:"
find "$APP_PATH" -type f | sort | while IFS= read -r f; do
    echo "    ${f#"$SCRIPT_DIR/"}"
done

# ── 8. Confirm .gitignore covers the .app ────────────────────────
if grep -qE '^\*\.app$|^OpenClay\.app$' "$SCRIPT_DIR/.gitignore" 2>/dev/null; then
    echo ""
    echo "  .gitignore: OK (*.app already excluded)"
else
    echo "OpenClay.app" >> "$SCRIPT_DIR/.gitignore"
    echo ""
    echo "  .gitignore: added OpenClay.app"
fi

echo ""
echo "  ✓ OpenClay.app is ready."
echo ""
echo "    Location : $APP_PATH"
echo "    To launch : double-click OpenClay.app"
echo "    To move   : drag it to your Applications folder"
echo "    To quit   : Cmd+Q or right-click → Quit in the Dock"
echo ""
