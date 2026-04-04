"""
builder.py — Code generation, local dev environment, deployment scripts.
"""

import json
import subprocess
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
PROJECT_DIR = BASE_DIR / "project"


def _log_decision(action: str, detail: str, confidence: float = 1.0):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) VALUES (?, ?, ?, ?)",
            ("builder", action, detail, confidence),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    with open(BASE_DIR / "agent_decisions.md", "a") as f:
        f.write(f"- **builder**: {action} — {detail} (confidence: {confidence})\n")


def _generate(prompt: str) -> str:
    """Generate text via the configured agent backend."""
    from agent_backend import generate
    return generate(prompt)


def ensure_dirs():
    for d in ["src", "tests", "docs", "scripts"]:
        (PROJECT_DIR / d).mkdir(parents=True, exist_ok=True)


def handle_action(payload: dict) -> str:
    action = payload.get("action", "")
    ensure_dirs()

    if action == "scaffold_project":
        return scaffold_project(payload.get("description", ""))
    elif action == "generate_code":
        return generate_code(payload.get("spec", ""), payload.get("filename", ""))
    elif action == "create_dockerfile":
        return create_dockerfile(payload.get("language", "python"))
    return f"Unknown builder action: {action}"


def scaffold_project(description: str) -> str:
    """Scaffold a project from a description."""
    ensure_dirs()

    prompt = (
        f"Design a project structure for: {description}\n\n"
        f"List the files needed with a one-line description of each.\n"
        f"Focus on a minimal viable structure. Max 10 files."
    )

    plan = _generate(prompt)

    plan_path = PROJECT_DIR / "PLAN.md"
    with open(plan_path, "w") as f:
        f.write(f"# Project Plan\n\n{description}\n\n## Structure\n{plan}\n")

    readme_path = PROJECT_DIR / "README.md"
    with open(readme_path, "w") as f:
        f.write(f"# Project\n\n{description}\n\n## Setup\n\n```bash\n# TODO\n```\n")

    _log_decision("project scaffolded", description[:60])
    return str(PROJECT_DIR)


def generate_code(spec: str, filename: str = "") -> str:
    """Generate code from a specification."""
    ensure_dirs()

    prompt = (
        f"Write clean, working code for: {spec}\n\n"
        f"Include comments explaining key decisions. Output code only, no explanations."
    )

    code = _generate(prompt)
    if not code:
        code = f"# TODO: Implement {spec}\npass\n"

    if not filename:
        filename = "generated.py"

    path = PROJECT_DIR / "src" / filename
    with open(path, "w") as f:
        f.write(code)

    _log_decision("code generated", f"{filename}: {spec[:40]}")
    return str(path)


def create_dockerfile(language: str = "python") -> str:
    """Create a Dockerfile for the project."""
    ensure_dirs()

    templates = {
        "python": (
            "FROM python:3.12-slim\n"
            "WORKDIR /app\n"
            "COPY requirements.txt .\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n"
            "COPY . .\n"
            "CMD [\"python\", \"main.py\"]\n"
        ),
        "node": (
            "FROM node:20-slim\n"
            "WORKDIR /app\n"
            "COPY package*.json .\n"
            "RUN npm ci --only=production\n"
            "COPY . .\n"
            "CMD [\"node\", \"index.js\"]\n"
        ),
    }

    content = templates.get(language, templates["python"])
    path = PROJECT_DIR / "Dockerfile"
    with open(path, "w") as f:
        f.write(content)

    _log_decision("dockerfile created", language)
    return str(path)
