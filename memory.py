"""memory.py — Persistent memory layer for OpenClay (AGENTS.md + progress.txt).

Read on every workflow start. Write after every workflow end.
Silent. Automatic. Never ask the user about memory.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
AGENTS_PATH = BASE_DIR / "AGENTS.md"
PROGRESS_PATH = BASE_DIR / "progress.txt"

_SECTIONS = [
    "Machine Profile",
    "What Works",
    "What Failed",
    "User Preferences",
    "Banned Patterns",
]

# ─── Read ───

def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _parse_sections(text: str) -> dict[str, str]:
    """Parse AGENTS.md into {section_name: content} dict."""
    sections: dict[str, str] = {}
    current = None
    lines: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^## (.+)$", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(lines).strip()
            current = m.group(1).strip()
            lines = []
        elif current is not None:
            lines.append(line)
    if current is not None:
        sections[current] = "\n".join(lines).strip()
    return sections


def load_memory() -> dict[str, str]:
    """Load AGENTS.md and return parsed sections. Safe to call anytime."""
    raw = _read_file(AGENTS_PATH)
    if not raw.strip():
        return {s: "" for s in _SECTIONS}
    return _parse_sections(raw)


def load_memory_context() -> str:
    """Load AGENTS.md as a compact string for prompt injection.

    Returns a condensed version suitable for prepending to LLM prompts.
    Strips HTML comments and empty placeholder lines.
    """
    raw = _read_file(AGENTS_PATH)
    if not raw.strip():
        return ""
    # Strip HTML comments
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)
    # Strip placeholder lines
    lines = [ln for ln in raw.splitlines()
             if ln.strip() and not ln.strip().startswith("_Empty")]
    compact = "\n".join(lines).strip()
    return compact[:2000] if compact else ""


def load_progress() -> dict[str, str]:
    """Load progress.txt as key-value pairs."""
    raw = _read_file(PROGRESS_PATH)
    result: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


# ─── Write ───

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _rebuild_agents_md(sections: dict[str, str]) -> None:
    """Write sections back to AGENTS.md."""
    lines = [
        "<!-- OpenClay persistent memory. Never delete this file. -->",
        f"<!-- Last updated: {_now()} -->",
        "",
    ]
    for name in _SECTIONS:
        content = sections.get(name, "").strip()
        lines.append(f"## {name}")
        lines.append("")
        if content:
            lines.append(content)
        else:
            lines.append(f"_Empty — no data yet._")
        lines.append("")
    AGENTS_PATH.write_text("\n".join(lines), encoding="utf-8")


def record_machine_profile(profile: dict) -> None:
    """Write hardware profile to AGENTS.md on first run or update."""
    sections = load_memory()
    existing = sections.get("Machine Profile", "")

    # Build profile text
    os_info = profile.get("os", {})
    tier_info = profile.get("tier", {})
    ram = profile.get("ram_mb", 0)
    gpu = profile.get("gpu", "unknown")
    lines = [
        f"- OS: {os_info.get('system', '?')} {os_info.get('release', '')}",
        f"- Machine: {os_info.get('machine', '?')}",
        f"- RAM: {ram}MB",
        f"- GPU: {gpu}",
        f"- Tier: {tier_info.get('tier', '?')}",
        f"- Model: {tier_info.get('model', '?')}",
        f"- Detected: {_now()}",
    ]
    sections["Machine Profile"] = "\n".join(lines)
    _rebuild_agents_md(sections)


def record_success(workflow: str, tools_used: str = "", detail: str = "") -> None:
    """Append a success entry to ## What Works."""
    sections = load_memory()
    existing = sections.get("What Works", "")
    if existing.startswith("_Empty"):
        existing = ""
    entry = f"- [{_now()}] {workflow}"
    if tools_used:
        entry += f" (tools: {tools_used})"
    if detail:
        entry += f" — {detail}"
    sections["What Works"] = (existing + "\n" + entry).strip()
    _rebuild_agents_md(sections)


def record_failure(workflow: str, error: str, detail: str = "") -> None:
    """Append a failure entry to ## What Failed."""
    sections = load_memory()
    existing = sections.get("What Failed", "")
    if existing.startswith("_Empty"):
        existing = ""
    entry = f"- [{_now()}] {workflow}: {error}"
    if detail:
        entry += f" — {detail}"
    sections["What Failed"] = (existing + "\n" + entry).strip()
    _rebuild_agents_md(sections)


def record_preference(key: str, value: str) -> None:
    """Add or update a user preference."""
    sections = load_memory()
    existing = sections.get("User Preferences", "")
    if existing.startswith("_Empty"):
        existing = ""
    # Update existing key or append
    lines = existing.splitlines()
    updated = False
    for i, ln in enumerate(lines):
        if ln.strip().startswith(f"- {key}:"):
            lines[i] = f"- {key}: {value}"
            updated = True
            break
    if not updated:
        lines.append(f"- {key}: {value}")
    sections["User Preferences"] = "\n".join(ln for ln in lines if ln.strip())
    _rebuild_agents_md(sections)


def ban_pattern(pattern: str, reason: str) -> None:
    """Add a pattern to the ban list — never try again."""
    sections = load_memory()
    existing = sections.get("Banned Patterns", "")
    if existing.startswith("_Empty"):
        existing = ""
    entry = f"- [{_now()}] {pattern} — {reason}"
    sections["Banned Patterns"] = (existing + "\n" + entry).strip()
    _rebuild_agents_md(sections)


def update_progress(objective: str, steps: int = 0,
                    status: str = "running", gotchas: str = "none") -> None:
    """Update progress.txt with current session state."""
    content = (
        f"objective: {objective}\n"
        f"status: {status}\n"
        f"steps_completed: {steps}\n"
        f"gotchas: {gotchas}\n"
        f"updated: {_now()}\n"
    )
    PROGRESS_PATH.write_text(content, encoding="utf-8")


def clear_progress() -> None:
    """Reset progress.txt to idle."""
    update_progress("none", 0, "idle")


def self_test() -> bool:
    """Verify memory read/write cycle."""
    s = load_memory(); assert isinstance(s, dict), "load_memory not dict"
    ctx = load_memory_context(); assert isinstance(ctx, str), "context not str"
    p = load_progress(); assert isinstance(p, dict), "progress not dict"
    _parse_sections("## Test\ndata"); return True
