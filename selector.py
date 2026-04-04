"""
selector.py — Maps intent JSON + hardware profile to configuration profile + tool stack.
Reads from data/intent.json and data/hardware.json.
Outputs data/stack.json and loads the appropriate profile overlay.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
PROFILES_DIR = BASE_DIR / "profiles"
QUEUE_DIR = BASE_DIR / "queue"

# Domain-to-profile mapping
DOMAIN_PROFILE_MAP = {
    "content": "creator",
    "research": "researcher",
    "automation": "operator",
    "development": "builder",
}

# Tool registry: tools indexed by capability, with install metadata
TOOL_REGISTRY = {
    # Content creation tools
    "markdown_editor": {
        "name": "markdown-editor",
        "package": {"brew": "marktext", "apt": "ghostwriter", "winget": "marktext"},
        "profiles": ["creator", "researcher"],
        "ram_min_mb": 2000,
        "description": "Visual markdown editor for writing",
    },
    "pandoc": {
        "name": "pandoc",
        "package": {"brew": "pandoc", "apt": "pandoc", "winget": "JohnMacFarlane.Pandoc"},
        "profiles": ["creator", "researcher"],
        "ram_min_mb": 512,
        "description": "Universal document converter",
    },
    "ffmpeg": {
        "name": "ffmpeg",
        "package": {"brew": "ffmpeg", "apt": "ffmpeg", "winget": "Gyan.FFmpeg"},
        "profiles": ["creator"],
        "ram_min_mb": 1000,
        "description": "Audio/video processing",
    },
    # Research tools
    "chromadb": {
        "name": "chromadb",
        "pip": "chromadb",
        "profiles": ["researcher"],
        "ram_min_mb": 4000,
        "description": "Local vector database for RAG",
    },
    "pdftotext": {
        "name": "pdftotext",
        "package": {"brew": "poppler", "apt": "poppler-utils"},
        "profiles": ["researcher"],
        "ram_min_mb": 256,
        "description": "PDF text extraction",
    },
    # Automation tools
    "n8n": {
        "name": "n8n",
        "npm": "n8n",
        "profiles": ["operator"],
        "ram_min_mb": 2000,
        "description": "Workflow automation engine",
    },
    # Development tools
    "git": {
        "name": "git",
        "package": {"brew": "git", "apt": "git", "winget": "Git.Git"},
        "profiles": ["builder"],
        "ram_min_mb": 256,
        "description": "Version control",
    },
    "docker": {
        "name": "docker",
        "package": {"brew": "docker", "apt": "docker.io", "winget": "Docker.DockerDesktop"},
        "profiles": ["builder"],
        "ram_min_mb": 4000,
        "description": "Container runtime",
    },
    # Universal tools (all profiles)
    "sqlite3_tool": {
        "name": "sqlite3",
        "package": {"brew": "sqlite", "apt": "sqlite3"},
        "profiles": ["creator", "researcher", "operator", "builder"],
        "ram_min_mb": 128,
        "description": "Local database",
    },
    "jq": {
        "name": "jq",
        "package": {"brew": "jq", "apt": "jq", "winget": "stedolan.jq"},
        "profiles": ["creator", "researcher", "operator", "builder"],
        "ram_min_mb": 64,
        "description": "JSON processor",
    },
}


def _log_decision(action: str, detail: str, confidence: float = 1.0):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) VALUES (?, ?, ?, ?)",
            ("selector", action, detail, confidence),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    decisions_path = BASE_DIR / "agent_decisions.md"
    line = f"- **selector**: {action} — {detail} (confidence: {confidence})\n"
    with open(decisions_path, "a") as f:
        f.write(line)


def select_profile(intent: dict) -> str:
    """Determine which profile to use based on intent."""
    # If intake already selected a profile (blank slate), use it
    if "profile" in intent and intent["profile"] in DOMAIN_PROFILE_MAP.values():
        return intent["profile"]

    domain = intent.get("domain", "other")
    if domain in DOMAIN_PROFILE_MAP:
        return DOMAIN_PROFILE_MAP[domain]

    # Fuzzy matching on goal text
    goal = intent.get("goal", "").lower()
    for domain, profile in DOMAIN_PROFILE_MAP.items():
        if domain in goal:
            return profile

    return "blank"


def select_tools(profile: str, hardware: dict) -> list[dict]:
    """Select tools that match the profile and fit the hardware."""
    ram_mb = hardware.get("ram_mb", 0)
    pkg_manager = hardware.get("package_manager", "unknown")
    selected = []

    for tool_id, tool in TOOL_REGISTRY.items():
        # Check profile match
        if profile != "blank" and profile not in tool["profiles"]:
            continue

        # Check RAM requirement
        if tool["ram_min_mb"] > ram_mb:
            continue

        # Determine install command
        install_cmd = None
        if "package" in tool and pkg_manager in tool["package"]:
            pkg = tool["package"][pkg_manager]
            if pkg_manager == "brew":
                install_cmd = f"brew install {pkg}"
            elif pkg_manager == "apt":
                install_cmd = f"sudo apt-get install -y {pkg}"
            elif pkg_manager == "winget":
                install_cmd = f"winget install {pkg}"
        elif "pip" in tool:
            install_cmd = f"pip3 install {tool['pip']}"
        elif "npm" in tool:
            install_cmd = f"npm install -g {tool['npm']}"

        selected.append({
            "id": tool_id,
            "name": tool["name"],
            "description": tool["description"],
            "install_cmd": install_cmd,
            "ram_min_mb": tool["ram_min_mb"],
        })

    return selected


def select_model(hardware: dict) -> dict:
    """Select the best LLM model for the hardware."""
    tier = hardware.get("tier", {})
    return {
        "model": tier.get("recommended_model", "phi3:mini"),
        "tier": tier.get("tier", "small"),
        "max_context": tier.get("max_context", 2048),
        "use_gpu": tier.get("use_gpu", False),
    }


def run() -> dict:
    """Run the full selection pipeline. Returns the stack configuration."""
    # Load inputs
    intent_path = DATA_DIR / "intent.json"
    hardware_path = DATA_DIR / "hardware.json"

    if not intent_path.exists():
        raise FileNotFoundError("No intent.json found — run intake first")
    if not hardware_path.exists():
        raise FileNotFoundError("No hardware.json found — run introspect first")

    with open(intent_path) as f:
        intent = json.load(f)
    with open(hardware_path) as f:
        hardware = json.load(f)

    # Select profile
    profile = select_profile(intent)
    _log_decision(
        f"selected profile: {profile}",
        f"domain={intent.get('domain')}, archetype={intent.get('archetype')}",
        0.85,
    )

    # Select tools
    tools = select_tools(profile, hardware)
    _log_decision(
        f"selected {len(tools)} tools",
        ", ".join(t["name"] for t in tools),
    )

    # Select model
    model = select_model(hardware)
    _log_decision(
        f"selected model: {model['model']}",
        f"tier={model['tier']}, context={model['max_context']}",
    )

    # Build stack config
    stack = {
        "profile": profile,
        "intent": intent,
        "model": model,
        "tools": tools,
        "hardware_tier": hardware.get("tier", {}),
    }

    # Load profile overlay if it exists
    profile_path = PROFILES_DIR / f"{profile}.json"
    if profile_path.exists():
        with open(profile_path) as f:
            stack["profile_config"] = json.load(f)

    # Save stack
    with open(DATA_DIR / "stack.json", "w") as f:
        json.dump(stack, f, indent=2)

    # Queue for installer
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    queue_item = {
        "source": "selector",
        "task_type": "install_stack",
        "payload": stack,
    }
    with open(QUEUE_DIR / "selector_complete.json", "w") as f:
        json.dump(queue_item, f, indent=2)

    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO queue_items (source, task_type, payload, status) VALUES (?, ?, ?, ?)",
            ("selector", "install_stack", json.dumps(stack), "pending"),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    return stack


if __name__ == "__main__":
    stack = run()
    print(json.dumps(stack, indent=2))
