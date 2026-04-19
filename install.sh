#!/usr/bin/env bash
# OpenClay — Local installer
# Usage: bash install.sh [--dry-run]
set -euo pipefail

DRY_RUN=false
for arg in "$@"; do [[ "$arg" == "--dry-run" ]] && DRY_RUN=true; done

run() {
  if $DRY_RUN; then echo "  [dry-run] $*"; else eval "$*"; fi
}

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║  OpenClay Installer — COANA Labs     ║"
echo "  ║  Local AI · No Cloud · Fully Private ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── 1. Check Python ──────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "  ✗ python3 not found. Install from https://python.org"; exit 1
fi
PYVER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  ✓ Python $PYVER"

# ── 2. Check / Install Ollama ────────────────────────────────────
if command -v ollama &>/dev/null; then
  echo "  ✓ Ollama already installed"
else
  echo "  → Installing Ollama..."
  if [[ "$(uname)" == "Darwin" ]]; then
    run "curl -fsSL https://ollama.com/install.sh | sh"
  else
    run "curl -fsSL https://ollama.com/install.sh | sh"
  fi
fi

# ── 3. Start Ollama ──────────────────────────────────────────────
if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
  echo "  → Starting Ollama daemon..."
  run "ollama serve &"
  sleep 3
fi

# ── 4. Pull default model ────────────────────────────────────────
DEFAULT_MODEL="qwen2.5:3b-instruct-q4_K_M"
if ollama list 2>/dev/null | grep -q "qwen2.5"; then
  echo "  ✓ Model already present"
else
  echo "  → Pulling $DEFAULT_MODEL (this may take a few minutes)..."
  run "ollama pull $DEFAULT_MODEL"
fi

# ── 5. Python dependencies ───────────────────────────────────────
echo "  → Checking Python dependencies..."
PKGS=(requests)
for pkg in "${PKGS[@]}"; do
  if python3 -c "import $pkg" &>/dev/null; then
    echo "  ✓ $pkg"
  else
    echo "  → Installing $pkg..."
    run "pip3 install --quiet $pkg"
  fi
done

# ── 6. Create required directories ──────────────────────────────
echo "  → Creating directories..."
for dir in logs data memory wiki tasks sandbox projects models; do
  run "mkdir -p $dir"
done

# ── 7. Done ──────────────────────────────────────────────────────
echo ""
echo "  ✅ OpenClay is ready."
echo ""
if $DRY_RUN; then
  echo "  (dry-run complete — no changes made)"
else
  echo "  Start the server:  python3 clay_server.py"
  echo "  Open in browser:   http://localhost:3000"
fi
echo ""
