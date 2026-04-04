"""
operator.py — Workflow automation, email, calendar, task management.
"""

import json
import subprocess
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
WORKFLOWS_DIR = BASE_DIR / "workflows"


def _log_decision(action: str, detail: str, confidence: float = 1.0):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) VALUES (?, ?, ?, ?)",
            ("operator", action, detail, confidence),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    with open(BASE_DIR / "agent_decisions.md", "a") as f:
        f.write(f"- **operator**: {action} — {detail} (confidence: {confidence})\n")


def _generate(prompt: str) -> str:
    """Generate text via the configured agent backend."""
    from agent_backend import generate
    return generate(prompt)


def ensure_dirs():
    for d in ["active", "templates", "logs"]:
        (WORKFLOWS_DIR / d).mkdir(parents=True, exist_ok=True)


def handle_action(payload: dict) -> str:
    action = payload.get("action", "")
    ensure_dirs()

    if action == "create_workflow":
        return create_workflow(payload.get("description", ""))
    elif action == "list_workflows":
        return list_workflows()
    elif action == "analyze_tasks":
        return analyze_tasks(payload.get("tasks", []))
    return f"Unknown operator action: {action}"


def create_workflow(description: str) -> str:
    """Create an automation workflow from a description."""
    ensure_dirs()

    prompt = (
        f"Design an automation workflow for: {description}\n\n"
        f"Output as JSON with these fields:\n"
        f"- name: short name\n"
        f"- trigger: what starts it\n"
        f"- steps: list of action objects with 'action' and 'config'\n"
        f"- schedule: cron expression if recurring, null if event-based\n"
        f"JSON only:"
    )

    raw = _generate(prompt)

    # Try to parse LLM output
    workflow = None
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            workflow = json.loads(raw[start:end])
    except (json.JSONDecodeError, ValueError):
        pass

    if not workflow:
        workflow = {
            "name": description[:40],
            "trigger": "manual",
            "steps": [{"action": "placeholder", "config": {"description": description}}],
            "schedule": None,
        }

    workflow["created_at"] = datetime.now().isoformat()
    workflow["status"] = "draft"

    slug = workflow["name"].lower().replace(" ", "-")[:30]
    filename = f"{slug}.json"
    path = WORKFLOWS_DIR / "active" / filename

    with open(path, "w") as f:
        json.dump(workflow, f, indent=2)

    _log_decision("workflow created", f"{workflow['name']}")
    return str(path)


def list_workflows() -> str:
    """List all active workflows."""
    ensure_dirs()
    active = WORKFLOWS_DIR / "active"
    workflows = []
    for f in active.glob("*.json"):
        with open(f) as fh:
            w = json.load(fh)
        workflows.append(f"- **{w.get('name', f.stem)}** — {w.get('trigger', 'manual')} ({w.get('status', 'unknown')})")

    return "\n".join(workflows) if workflows else "No workflows yet."


def analyze_tasks(tasks: list) -> str:
    """Analyze a list of tasks and suggest automation opportunities."""
    if not tasks:
        return "No tasks provided."

    task_text = "\n".join(f"- {t}" for t in tasks)
    prompt = (
        f"Analyze these tasks and identify which ones can be automated:\n{task_text}\n\n"
        f"For each automatable task, explain how to automate it and estimate time saved."
    )

    result = _generate(prompt)
    return result or "Analysis pending — model loading."
