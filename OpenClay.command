#!/bin/bash
# OpenClay launcher — double-click to start
cd "$(dirname "$0")"
source venv/bin/activate 2>/dev/null || true
python3 clay_server.py &
sleep 3
open http://localhost:3000
