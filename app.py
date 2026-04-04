"""
app.py — OpenClay orchestrator.
Zero business logic. Sequences modules and launches the system.
Single entry point: python app.py
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


def print_banner():
    print("""
    ╔═══════════════════════════════════╗
    ║          O P E N C L A Y          ║
    ║   Local AI Infrastructure Builder ║
    ╚═══════════════════════════════════╝
    """)


def phase_introspect():
    """Phase 1: Detect hardware."""
    print("  [1/6] Scanning hardware...", end=" ", flush=True)
    from introspect import run as introspect_run
    profile = introspect_run()
    tier = profile.get("tier", {}).get("tier", "unknown")
    ram = profile.get("ram_mb", 0)
    print(f"done. ({ram}MB RAM, tier: {tier})")
    return profile


def phase_intake_demo(config: dict) -> dict:
    """Phase 2 (demo): Load pre-selected sample input, skip conversation."""
    demo_asset = config.get("demo_asset", "demo_assets/sample_intake.json")
    demo_path = BASE_DIR / demo_asset
    print(f"\n  [2/6] Demo mode — loading {demo_asset}...", end=" ", flush=True)

    if not demo_path.exists():
        print(f"MISSING. Falling back to live intake.")
        return phase_intake()

    with open(demo_path) as f:
        intent = json.load(f)

    # Save it exactly as intake would
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / "intent.json", "w") as f:
        json.dump(intent, f, indent=2)
    queue_item = {"source": "intake", "task_type": "select_profile", "payload": intent}
    with open(QUEUE_DIR / "intake_complete.json", "w") as f:
        json.dump(queue_item, f, indent=2)

    print(f"done. (goal: {intent.get('goal', '')[:50]})")
    return intent


def phase_intake():
    """Phase 2: Conversational onboarding."""
    print("\n  [2/6] Let's figure out what to build.\n")
    from intake import IntakeSession
    session = IntakeSession()

    # Check if intent already exists (resuming)
    intent_path = DATA_DIR / "intent.json"
    if intent_path.exists():
        with open(intent_path) as f:
            intent = json.load(f)
        print(f"  Resuming with existing intent: {intent.get('goal', '')[:60]}")
        confirm = input("  Continue with this? (y/n): ").strip().lower()
        if confirm in ("y", "yes", ""):
            return intent

    while not session.complete:
        user_input = input("  You: ").strip()
        if not user_input:
            continue
        result = session.process(user_input)
        if result["response"]:
            print(f"\n  OpenClay: {result['response']}\n")
        if result["complete"]:
            return result["intent"]

    return session.intent


def phase_select(intent: dict):
    """Phase 3: Map intent to stack."""
    print("  [3/6] Selecting your stack...", end=" ", flush=True)
    from selector import run as selector_run
    stack = selector_run()
    profile = stack.get("profile", "unknown")
    tools = stack.get("tools", [])
    model = stack.get("model", {}).get("model", "none")
    print(f"done. (profile: {profile}, {len(tools)} tools, model: {model})")
    return stack


def phase_install(stack: dict):
    """Phase 4: Install everything."""
    print("  [4/6] Installing your stack (this may take a few minutes)...")
    from installer import run as installer_run
    results = installer_run()

    installed = sum(1 for t in results.get("tools", [])
                   if t["status"] in ("installed", "already_installed"))
    total = len(results.get("tools", []))
    model_status = results.get("model", {}).get("status", "unknown")
    print(f"         Tools: {installed}/{total} ready. Model: {model_status}.")
    return results


def phase_first_action(stack: dict):
    """Phase 5: Execute first autonomous action."""
    print("  [5/6] Running first action...", end=" ", flush=True)
    from agent import run_first_action
    result = run_first_action(stack)
    print(f"done.")
    print(f"         → {result}")
    return result


def phase_launch(stack: dict):
    """Phase 6: Start agent loop and panel."""
    print("  [6/6] Launching panel and agent...\n")

    # Start agent loop in background
    from agent import run_loop
    agent_thread = threading.Thread(target=run_loop, daemon=True)
    agent_thread.start()

    # Launch panel (blocks)
    try:
        from panel import launch
        launch()
    except ImportError:
        print("  Gradio not available. Agent is running in background.")
        print("  Install gradio with: pip3 install gradio")
        print("  Press Ctrl+C to stop.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n  Shutting down.")
    except Exception as e:
        print(f"  Panel failed to launch: {e}")
        print("  Agent is running in background. Press Ctrl+C to stop.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n  Shutting down.")


def main():
    print_banner()
    config = load_config()
    demo = config.get("demo_mode", False)

    if demo:
        print("  *** DEMO MODE ***\n")

    # Phase 1: Hardware detection (silent)
    hardware = phase_introspect()

    # Phase 2: Intake — demo loads sample file, live runs conversation
    intent = phase_intake_demo(config) if demo else phase_intake()

    # Phase 3: Stack selection
    stack = phase_select(intent)

    # Phase 4: Installation
    install_results = phase_install(stack)

    # Phase 5: First autonomous action
    first_action = phase_first_action(stack)

    # Phase 6: Launch panel + agent loop
    phase_launch(stack)


if __name__ == "__main__":
    main()
