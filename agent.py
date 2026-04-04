"""
agent.py — Core autonomous loop.
Reads from /queue folder, executes tasks, logs decisions.
This is the engine that keeps OpenClay running after setup.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
QUEUE_DIR = BASE_DIR / "queue"
LOGS_DIR = BASE_DIR / "logs"


def _log_decision(action: str, detail: str, confidence: float = 1.0):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) VALUES (?, ?, ?, ?)",
            ("agent", action, detail, confidence),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    decisions_path = BASE_DIR / "agent_decisions.md"
    line = f"- **agent**: {action} — {detail} (confidence: {confidence})\n"
    with open(decisions_path, "a") as f:
        f.write(line)


def _generate(prompt: str, model: str | None = None) -> str:
    """Generate text via the configured agent backend."""
    from agent_backend import generate
    return generate(prompt, model=model)


def load_stack() -> dict:
    """Load the current stack configuration."""
    stack_path = DATA_DIR / "stack.json"
    if stack_path.exists():
        with open(stack_path) as f:
            return json.load(f)
    return {}


def load_profile_module(profile: str):
    """Dynamically load the profile-specific module."""
    import importlib
    try:
        mod = importlib.import_module(f"{profile}_profile")
        return mod
    except ImportError:
        return None


def scan_queue() -> list[dict]:
    """Scan the queue folder for pending tasks."""
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    tasks = []
    for f in sorted(QUEUE_DIR.iterdir()):
        if f.suffix == ".json" and not f.name.startswith("."):
            try:
                with open(f) as fh:
                    task = json.load(fh)
                task["_file"] = str(f)
                tasks.append(task)
            except (json.JSONDecodeError, IOError):
                continue
    return tasks


def complete_task(task: dict):
    """Mark a task as completed — move its file to processed."""
    file_path = task.get("_file")
    if file_path and os.path.exists(file_path):
        processed_dir = QUEUE_DIR / "processed"
        processed_dir.mkdir(exist_ok=True)
        dest = processed_dir / Path(file_path).name
        os.rename(file_path, str(dest))

    # Update SQLite
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "UPDATE queue_items SET status = 'completed', completed_at = ? "
            "WHERE source = ? AND task_type = ? AND status = 'pending'",
            (datetime.now().isoformat(), task.get("source"), task.get("task_type")),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def execute_task(task: dict) -> dict:
    """Execute a single queued task. Returns result dict."""
    task_type = task.get("task_type", "unknown")
    source = task.get("source", "unknown")
    payload = task.get("payload", {})

    _log_decision(f"executing {task_type}", f"from {source}", 0.9)

    result = {"task_type": task_type, "status": "completed", "output": None}

    if task_type == "select_profile":
        # Run selector
        try:
            from selector import run as run_selector
            stack = run_selector()
            result["output"] = f"Profile: {stack.get('profile')}, {len(stack.get('tools', []))} tools selected"
        except Exception as e:
            result["status"] = "failed"
            result["output"] = str(e)

    elif task_type == "install_stack":
        # Run installer
        try:
            from installer import run as run_installer
            install_results = run_installer()
            installed = sum(1 for t in install_results.get("tools", [])
                          if t["status"] in ("installed", "already_installed"))
            result["output"] = f"Installed {installed} tools, model: {install_results.get('model', {}).get('status')}"
        except Exception as e:
            result["status"] = "failed"
            result["output"] = str(e)

    elif task_type == "start_agent":
        # Agent is now running — this is the signal to begin autonomous work
        result["output"] = "Agent loop started"

    elif task_type == "generate":
        # Generic generation task
        prompt = payload.get("prompt", "")
        output_file = payload.get("output_file")
        if prompt:
            generated = _generate(prompt)
            if output_file:
                Path(output_file).parent.mkdir(parents=True, exist_ok=True)
                with open(output_file, "w") as f:
                    f.write(generated)
            result["output"] = generated[:200] if generated else "generation failed"
        else:
            result["status"] = "failed"
            result["output"] = "no prompt provided"

    elif task_type == "profile_action":
        # Delegate to profile module
        stack = load_stack()
        profile = stack.get("profile", "blank")
        mod = load_profile_module(profile)
        if mod and hasattr(mod, "handle_action"):
            try:
                result["output"] = mod.handle_action(payload)
            except Exception as e:
                result["status"] = "failed"
                result["output"] = str(e)
        else:
            result["status"] = "skipped"
            result["output"] = f"no handler for profile {profile}"

    else:
        result["status"] = "unknown_type"
        result["output"] = f"unrecognized task type: {task_type}"

    complete_task(task)
    _log_decision(
        f"{task_type} {result['status']}",
        str(result.get("output", ""))[:100],
        1.0 if result["status"] == "completed" else 0.5,
    )

    return result


def run_first_action(stack: dict) -> str:
    """Delegate to first_action module."""
    from first_action import run as _run_first
    return _run_first(stack)


def run_loop(once: bool = False):
    """
    Main agent loop. Scans queue, executes tasks, sleeps.
    Set once=True to process current queue and exit.
    """
    _log_decision("agent loop started", f"mode={'once' if once else 'continuous'}")

    while True:
        tasks = scan_queue()
        if tasks:
            for task in tasks:
                execute_task(task)
        elif once:
            break

        if once:
            break

        time.sleep(5)


if __name__ == "__main__":
    import sys
    if "--once" in sys.argv:
        run_loop(once=True)
    else:
        run_loop()
