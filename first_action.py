"""
first_action.py — Execute the first autonomous action after setup.
This is what gives the user their "wait, it already did that?" moment.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"


def _generate(prompt: str, model: str | None = None) -> str:
    """Generate text via the configured agent backend."""
    from agent_backend import generate
    return generate(prompt, model=model)


def _log_decision(action: str, detail: str, confidence: float = 1.0):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) VALUES (?, ?, ?, ?)",
            ("first_action", action, detail, confidence),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    with open(BASE_DIR / "agent_decisions.md", "a") as f:
        f.write(f"- **first_action**: {action} — {detail} (confidence: {confidence})\n")


def _write_output(heading: str, body: str) -> str:
    output_path = DATA_DIR / "first_action_output.md"
    with open(output_path, "w") as f:
        f.write(f"# {heading}\n\n{body}\n")
    return str(output_path)


def run(stack: dict) -> str:
    """Execute the first autonomous action based on the profile."""
    profile = stack.get("profile", "blank")
    intent = stack.get("intent", {})
    goal = intent.get("goal", "")

    if profile == "creator":
        return _creator_first_action(intent, goal)
    elif profile == "researcher":
        return _researcher_first_action()
    elif profile == "operator":
        return _operator_first_action(goal)
    elif profile == "builder":
        return _builder_first_action(goal)
    return _blank_first_action(goal)


def _creator_first_action(intent: dict, goal: str) -> str:
    content_intent = intent.get("content_intent", "strategy_needed")

    if content_intent == "post_ready":
        prompt = (
            f"The user has content ready to post. Their description: {goal}\n\n"
            f"Write an Instagram caption with:\n"
            f"- A scroll-stopping opening hook\n"
            f"- 2-3 sentence body\n- Call to action\n"
            f"- 15-20 relevant hashtags (mix broad + niche)\n\n"
            f"Then add: 'Drop your media files into the panel to attach them.'"
        )
        result = _generate(prompt)
        if result:
            _write_output("Caption + Hashtags",
                          f"{result}\n\n---\n*Drop your media files into the panel to attach.*")
            _log_decision("caption generated", goal[:60])
            return "Caption + hashtags ready. Drop your media into the panel."
    else:
        prompt = (
            f"Create a brief, actionable content plan for: {goal}\n"
            f"Include 3 specific content pieces they should create first, with titles.\n"
            f"Keep it under 200 words. Be specific and practical."
        )
        result = _generate(prompt)
        if result:
            _write_output("Your Content Plan", result)
            _log_decision("content plan generated", goal[:60])
            return f"Generated your content plan based on: {goal}"
    return "Ready. Waiting for first task."


def _researcher_first_action() -> str:
    kb_dir = BASE_DIR / "knowledge_base"
    for d in ["inbox", "processed", "notes"]:
        (kb_dir / d).mkdir(parents=True, exist_ok=True)
    readme = (
        "# Knowledge Base\n\n"
        "Drop documents into `inbox/` — they'll be processed automatically.\n\n"
        "- `inbox/` — new documents to process\n"
        "- `processed/` — documents that have been ingested\n"
        "- `notes/` — AI-generated summaries and connections\n"
    )
    with open(kb_dir / "README.md", "w") as f:
        f.write(readme)
    _log_decision("knowledge base created", "inbox/processed/notes structure")
    return "Created your knowledge base. Drop documents into knowledge_base/inbox/."


def _operator_first_action(goal: str) -> str:
    prompt = (
        f"Analyze this automation goal and list the top 3 workflows to automate: {goal}\n"
        f"For each, name the trigger, the action, and estimated time saved per week.\n"
        f"Keep it under 200 words."
    )
    result = _generate(prompt)
    if result:
        _write_output("Automation Plan", result)
        _log_decision("automation plan generated", goal[:60])
        return f"Generated your automation plan based on: {goal}"
    return "Ready. Waiting for first task."


def _builder_first_action(goal: str) -> str:
    project_dir = BASE_DIR / "project"
    for d in ["src", "tests", "docs"]:
        (project_dir / d).mkdir(parents=True, exist_ok=True)
    with open(project_dir / "README.md", "w") as f:
        f.write(f"# Project\n\n{goal}\n\n## Getting Started\n\nTODO\n")
    _log_decision("project scaffolded", goal[:60])
    return "Scaffolded your project structure in project/."


def _blank_first_action(goal: str) -> str:
    prompt = f"The user wants to: {goal}\nSuggest 3 concrete first steps. Be specific."
    result = _generate(prompt)
    if result:
        _write_output("Next Steps", result)
        _log_decision("next steps generated", goal[:60])
        return f"Generated next steps for: {goal}"
    return "Ready. Waiting for first task."
