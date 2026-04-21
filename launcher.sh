#!/usr/bin/env bash
# launcher.sh — OpenClay startup logic
# This file is the source of truth. create_app.sh copies it into
# OpenClay.app/Contents/Resources/ with PROJECT_DIR substituted.
#
# Called by the AppleScript wrapper on double-click.
# Exits 0 on success (server up + browser open).
# Exits 1 on timeout — AppleScript shows a native error dialog.

# PROJECT_DIR is replaced by create_app.sh at build time.
PROJECT_DIR="__PROJECT_DIR__"

LOG_FILE="/tmp/openclay.log"
PID_FILE="/tmp/openclay_server.pid"
OLLAMA_LOG="/tmp/openclay_ollama.log"

# ── Extend PATH so python3 / ollama are findable ──────────────────
export PATH="/usr/local/bin:/opt/homebrew/bin:/Library/Frameworks/Python.framework/Versions/3.13/bin:/Library/Frameworks/Python.framework/Versions/3.12/bin:/Library/Frameworks/Python.framework/Versions/3.11/bin:/Library/Frameworks/Python.framework/Versions/3.10/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

# ── 1. Ensure Ollama is running ───────────────────────────────────
if command -v ollama >/dev/null 2>&1; then
    if ! ollama list >/dev/null 2>&1; then
        ollama serve >>"$OLLAMA_LOG" 2>&1 &
        sleep 3
    fi
fi

# ── 2. Kill any stale server from a previous launch ───────────────
if [ -f "$PID_FILE" ]; then
    old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "$old_pid" ]; then
        kill "$old_pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
fi

# Give a moment for port 3000 to release if we just killed a stale server
sleep 1

# ── 3. Activate venv (if present) and start clay_server.py ───────
cd "$PROJECT_DIR"
if [ -f "$PROJECT_DIR/venv/bin/activate" ]; then
    # shellcheck source=/dev/null
    source "$PROJECT_DIR/venv/bin/activate"
fi

python3 "$PROJECT_DIR/clay_server.py" >>"$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

# ── 4. Poll localhost:3000 using Python stdlib — no curl needed ───
# Tries every second for up to 20 seconds.
python3 - <<'PYEOF'
import urllib.request, urllib.error, time, sys

for attempt in range(20):
    try:
        urllib.request.urlopen("http://localhost:3000", timeout=1)
        sys.exit(0)
    except Exception:
        time.sleep(1)

sys.exit(1)
PYEOF

POLL_STATUS=$?

if [ "$POLL_STATUS" -ne 0 ]; then
    exit 1
fi

# ── 5. Open the default browser ───────────────────────────────────
open "http://localhost:3000"

# ── 6. macOS notification ─────────────────────────────────────────
osascript -e 'display notification "OpenClay is running" with title "OpenClay" sound name "Glass"' 2>/dev/null || true

exit 0
