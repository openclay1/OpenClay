#!/bin/bash
# create_app.sh — build OpenClay.app for macOS
# Run once: bash create_app.sh
# Then double-click OpenClay.app to launch.

DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Building OpenClay.app in: $DIR"

osacompile -o "$DIR/OpenClay.app" -e "
do shell script \"cd '$DIR' && bash '$DIR/OpenClay.command' > /tmp/openclay.log 2>&1 &\"
delay 3
open location \"http://localhost:3000\"
"

echo "Done. OpenClay.app created."
echo "Double-click OpenClay.app to launch."
