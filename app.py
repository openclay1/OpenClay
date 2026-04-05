"""
app.py — OpenClay entry point.
Detects hardware, installs what's needed, opens the browser.
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
QUEUE_DIR = BASE_DIR / "queue"
CONFIG_PATH = BASE_DIR / "config.json"

os.chdir(str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR))


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {}


def setup():
    """Detect hardware, write to memory, install silently."""
    # Hardware detection
    profile = {}
    try:
        from introspect import run as introspect_run
        profile = introspect_run()
    except Exception:
        pass

    # Write machine profile to AGENTS.md (first run populates, later runs update)
    try:
        from memory import record_machine_profile
        record_machine_profile(profile)
    except Exception:
        pass

    # Stack selection
    try:
        from selector import run as selector_run
        stack = selector_run()
    except Exception:
        stack = {}

    # Silent installation
    try:
        from installer import run as installer_run
        installer_run()
    except Exception:
        pass

    return stack


def main():
    print("OpenClay is starting... ⚡")
    config = load_config()
    demo = config.get("demo_mode", False)

    # Demo mode: load sample intent
    if demo:
        demo_path = BASE_DIR / config.get("demo_asset", "demo_assets/sample_intake.json")
        if demo_path.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            QUEUE_DIR.mkdir(parents=True, exist_ok=True)
            with open(demo_path) as f:
                intent = json.load(f)
            with open(DATA_DIR / "intent.json", "w") as f:
                json.dump(intent, f, indent=2)

    # Setup: hardware + install (silent)
    stack = setup()

    # Start agent loop in background
    try:
        from agent import run_loop
        agent_thread = threading.Thread(target=run_loop, daemon=True)
        agent_thread.start()
    except Exception:
        pass

    # One clean line, then open the browser
    print("\n  ✓ OpenClay ready → http://127.0.0.1:7861\n")

    # Launch panel (blocks)
    try:
        from panel import launch
        launch()
    except ImportError:
        print("  Gradio not installed. Run: pip3 install gradio")
    except KeyboardInterrupt:
        print("\n  Stopped.")
    except Exception as e:
        print(f"  Error: {e}")


if __name__ == "__main__":
    main()
