"""
creator.py — Content pipeline profile module.
Handles content creation, publishing prep, and revenue engine tasks.
Loaded by agent.py when profile is "creator".
"""

import json
import subprocess
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
QUEUE_DIR = BASE_DIR / "queue"
CONTENT_DIR = BASE_DIR / "content"


def _log_decision(action: str, detail: str, confidence: float = 1.0):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) VALUES (?, ?, ?, ?)",
            ("creator", action, detail, confidence),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    decisions_path = BASE_DIR / "agent_decisions.md"
    line = f"- **creator**: {action} — {detail} (confidence: {confidence})\n"
    with open(decisions_path, "a") as f:
        f.write(line)


def _generate(prompt: str) -> str:
    """Generate text via the configured agent backend."""
    from agent_backend import generate
    return generate(prompt)


def ensure_dirs():
    """Create content pipeline directories."""
    for subdir in ["drafts", "published", "ideas", "media", "templates"]:
        (CONTENT_DIR / subdir).mkdir(parents=True, exist_ok=True)


def handle_action(payload: dict) -> str:
    """Handle a profile-specific action from the agent."""
    action = payload.get("action", "")
    ensure_dirs()

    if action == "generate_outline":
        return generate_outline(payload.get("topic", ""), payload.get("format", "blog"))
    elif action == "draft_content":
        return draft_content(payload.get("outline_path", ""))
    elif action == "convert_format":
        return convert_format(
            payload.get("source_path", ""),
            payload.get("target_format", "html"),
        )
    elif action == "generate_ideas":
        return generate_ideas(payload.get("niche", ""), payload.get("count", 5))
    elif action == "generate_caption":
        return generate_caption_hashtags(
            payload.get("topic", ""),
            payload.get("platform", "instagram"),
        )
    else:
        return f"Unknown creator action: {action}"


def generate_outline(topic: str, content_format: str = "blog") -> str:
    """Generate a content outline for a given topic."""
    ensure_dirs()
    prompt = (
        f"Create a detailed outline for a {content_format} about: {topic}\n"
        f"Include:\n"
        f"- A compelling title\n"
        f"- 4-6 main sections with subpoints\n"
        f"- A hook for the opening\n"
        f"- A call to action for the ending\n"
        f"Format as markdown."
    )

    outline = _generate(prompt)
    if not outline:
        # Template fallback
        outline = (
            f"# {topic}\n\n"
            f"## Introduction\n- Hook: [opening that grabs attention]\n\n"
            f"## Main Point 1\n- Detail\n- Example\n\n"
            f"## Main Point 2\n- Detail\n- Example\n\n"
            f"## Main Point 3\n- Detail\n- Example\n\n"
            f"## Conclusion\n- Summary\n- Call to action\n"
        )

    slug = topic.lower().replace(" ", "-")[:40]
    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"{timestamp}-{slug}-outline.md"
    path = CONTENT_DIR / "drafts" / filename

    with open(path, "w") as f:
        f.write(outline)

    _log_decision("outline generated", f"{topic} -> {filename}")
    return str(path)


def draft_content(outline_path: str) -> str:
    """Generate a full draft from an outline."""
    ensure_dirs()
    outline_file = Path(outline_path)
    if not outline_file.exists():
        return f"Outline not found: {outline_path}"

    with open(outline_file) as f:
        outline = f.read()

    prompt = (
        f"Write a complete blog post based on this outline:\n\n{outline}\n\n"
        f"Write in a conversational, engaging tone. Include specific examples.\n"
        f"Target 800-1200 words. Format as markdown."
    )

    draft = _generate(prompt)
    if not draft:
        draft = f"[Draft pending — outline loaded from {outline_path}]\n\n{outline}"

    draft_name = outline_file.stem.replace("-outline", "-draft") + ".md"
    draft_path = CONTENT_DIR / "drafts" / draft_name

    with open(draft_path, "w") as f:
        f.write(draft)

    _log_decision("draft generated", f"{outline_path} -> {draft_name}")
    return str(draft_path)


def convert_format(source_path: str, target_format: str = "html") -> str:
    """Convert content to another format using pandoc."""
    source = Path(source_path)
    if not source.exists():
        return f"Source not found: {source_path}"

    output_ext = {"html": ".html", "pdf": ".pdf", "docx": ".docx"}.get(target_format, ".html")
    output_path = CONTENT_DIR / "published" / (source.stem + output_ext)

    try:
        result = subprocess.run(
            ["pandoc", str(source), "-o", str(output_path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            _log_decision("format converted", f"{source_path} -> {output_path}")
            return str(output_path)
        else:
            _log_decision("pandoc failed", result.stderr[:100], 0.5)
            return f"Conversion failed: {result.stderr[:100]}"
    except FileNotFoundError:
        return "pandoc not installed — install it to convert formats"
    except Exception as e:
        return f"Conversion error: {e}"


def generate_ideas(niche: str, count: int = 5) -> str:
    """Generate content ideas for a niche."""
    ensure_dirs()
    prompt = (
        f"Generate {count} unique, specific content ideas for the niche: {niche}\n"
        f"For each idea, include:\n"
        f"- Title\n"
        f"- One-sentence hook\n"
        f"- Target audience\n"
        f"- Estimated engagement potential (low/medium/high)\n"
        f"Format as a numbered markdown list."
    )

    ideas = _generate(prompt)
    if not ideas:
        ideas = f"# Content Ideas: {niche}\n\n1. [Generate ideas after model is ready]\n"

    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"{timestamp}-ideas-{niche.lower().replace(' ', '-')[:20]}.md"
    path = CONTENT_DIR / "ideas" / filename

    with open(path, "w") as f:
        f.write(ideas)

    _log_decision("ideas generated", f"{count} ideas for {niche}")
    return str(path)


def generate_caption_hashtags(topic: str, platform: str = "instagram") -> str:
    """Generate a caption + hashtags for content that's ready to post."""
    ensure_dirs()
    prompt = (
        f"Write a {platform} caption for this content: {topic}\n\n"
        f"Requirements:\n"
        f"- Opening hook (first line must stop the scroll)\n"
        f"- 2-3 sentence body with a clear message\n"
        f"- Call to action\n"
        f"- 15-20 relevant hashtags (mix of broad and niche)\n\n"
        f"Format:\n[CAPTION]\n\n[HASHTAGS]"
    )

    result = _generate(prompt)
    if not result:
        result = (
            f"[Caption for: {topic}]\n\n"
            f"Drop your media files and describe what's in them "
            f"— I'll write the caption.\n\n"
            f"#content #post #ready"
        )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    filename = f"{timestamp}-caption.md"
    path = CONTENT_DIR / "drafts" / filename

    with open(path, "w") as f:
        f.write(f"# Caption — {platform.title()}\n\n{result}\n")

    _log_decision("caption + hashtags generated", f"{platform}: {topic[:40]}")
    return str(path)


def get_pipeline_status() -> dict:
    """Return current content pipeline status."""
    ensure_dirs()
    return {
        "drafts": len(list((CONTENT_DIR / "drafts").glob("*.md"))),
        "published": len(list((CONTENT_DIR / "published").glob("*"))),
        "ideas": len(list((CONTENT_DIR / "ideas").glob("*.md"))),
        "media_files": len(list((CONTENT_DIR / "media").glob("*"))),
    }
