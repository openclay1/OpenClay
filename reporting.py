"""
reporting.py — Agent decisions log, panel data updates, weekly summaries.
Reads from SQLite agent_log. Produces human-readable reports.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
LOGS_DIR = BASE_DIR / "logs"


def get_recent_decisions(hours: int = 24) -> list[dict]:
    """Get agent decisions from the last N hours."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            "SELECT module, action, detail, confidence, created_at "
            "FROM agent_log WHERE created_at > ? ORDER BY created_at DESC",
            (cutoff,),
        ).fetchall()
        conn.close()
        return [
            {
                "module": r[0],
                "action": r[1],
                "detail": r[2],
                "confidence": r[3],
                "timestamp": r[4],
            }
            for r in rows
        ]
    except Exception:
        return []


def get_queue_status() -> dict:
    """Get current queue statistics."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        pending = conn.execute(
            "SELECT COUNT(*) FROM queue_items WHERE status = 'pending'"
        ).fetchone()[0]
        completed = conn.execute(
            "SELECT COUNT(*) FROM queue_items WHERE status = 'completed'"
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM queue_items WHERE status = 'failed'"
        ).fetchone()[0]
        conn.close()
        return {"pending": pending, "completed": completed, "failed": failed}
    except Exception:
        return {"pending": 0, "completed": 0, "failed": 0}


def get_panel_data() -> dict:
    """
    Generate data for the four-section panel:
    1. What was built
    2. What it's already doing
    3. What it needs from you
    4. Drop zone action
    """
    # Load stack info
    stack = {}
    stack_path = DATA_DIR / "stack.json"
    if stack_path.exists():
        with open(stack_path) as f:
            stack = json.load(f)

    # Load install results
    install = {}
    install_path = DATA_DIR / "install_results.json"
    if install_path.exists():
        with open(install_path) as f:
            install = json.load(f)

    # Section 1: What was built
    profile = stack.get("profile", "unknown")
    intent = stack.get("intent", {})
    tools = stack.get("tools", [])
    model = stack.get("model", {})

    built_items = []
    built_items.append(f"Profile: **{profile}** — matched to your goal")
    if model.get("model"):
        built_items.append(f"AI Model: **{model['model']}** — runs locally, no cloud needed")
    for tool in tools:
        status = "installed"
        for ir in install.get("tools", []):
            if ir.get("name") == tool.get("name"):
                status = ir.get("status", "pending")
                break
        built_items.append(f"{tool['name']}: {tool['description']} ({status})")

    # Section 2: What it's already doing
    first_action_path = DATA_DIR / "first_action_output.md"
    already_doing = ""
    if first_action_path.exists():
        with open(first_action_path) as f:
            already_doing = f.read()
    else:
        already_doing = "Setting up your workspace..."

    # Section 3: What it needs from you
    needs = []
    for cred in install.get("credentials_needed", []):
        needs.append({
            "key": cred.get("key", ""),
            "label": cred.get("label", ""),
            "required": cred.get("required", False),
        })

    # Section 4: Drop zone
    drop_zone = _get_drop_zone_action(profile, intent)

    return {
        "what_was_built": built_items,
        "what_its_doing": already_doing,
        "what_it_needs": needs,
        "drop_zone": drop_zone,
        "queue_status": get_queue_status(),
    }


def _get_drop_zone_action(profile: str, intent: dict) -> dict:
    """Determine the single most useful action for the drop zone."""
    if profile == "creator":
        return {
            "label": "Drop a topic or idea here to start creating",
            "action_type": "text_input",
            "handler": "generate_outline",
        }
    elif profile == "researcher":
        return {
            "label": "Drop a PDF or document here to add to your knowledge base",
            "action_type": "file_upload",
            "handler": "ingest_document",
        }
    elif profile == "operator":
        return {
            "label": "Describe a repetitive task to automate",
            "action_type": "text_input",
            "handler": "create_workflow",
        }
    elif profile == "builder":
        return {
            "label": "Describe what you want to build",
            "action_type": "text_input",
            "handler": "scaffold_project",
        }
    else:
        return {
            "label": "Tell me what to do next",
            "action_type": "text_input",
            "handler": "generic_task",
        }


def generate_weekly_summary() -> str:
    """Generate a weekly summary of agent activity."""
    decisions = get_recent_decisions(hours=168)  # 7 days
    queue = get_queue_status()

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    summary_lines = [
        f"# Weekly Summary — {datetime.now().strftime('%Y-%m-%d')}\n",
        f"## Activity",
        f"- Decisions made: {len(decisions)}",
        f"- Tasks completed: {queue['completed']}",
        f"- Tasks pending: {queue['pending']}",
        f"- Tasks failed: {queue['failed']}",
        "",
        "## Key Decisions",
    ]

    # Group by module
    modules = {}
    for d in decisions[:50]:  # Cap at 50
        mod = d["module"]
        if mod not in modules:
            modules[mod] = []
        modules[mod].append(d)

    for mod, decs in modules.items():
        summary_lines.append(f"\n### {mod}")
        for d in decs[:10]:
            summary_lines.append(f"- {d['action']}: {d['detail'][:80]}")

    summary = "\n".join(summary_lines)

    filename = f"weekly-{datetime.now().strftime('%Y%m%d')}.md"
    with open(LOGS_DIR / filename, "w") as f:
        f.write(summary)

    return summary


if __name__ == "__main__":
    data = get_panel_data()
    print(json.dumps(data, indent=2, default=str))
