"""wiki_engine.py — Karpathy-style LLM wiki for grounded tweet generation."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
WIKI_DIR = BASE_DIR / "wiki"
VOICE_PATH = WIKI_DIR / "brand" / "voice.md"
LOG_PATH = WIKI_DIR / "log.md"
INDEX_PATH = WIKI_DIR / "index.md"
POSTS_DIR = WIKI_DIR / "posts"
TOPICS_DIR = WIKI_DIR / "topics"
SOURCES_DIR = WIKI_DIR / "sources"

# ─── Helpers ───

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _append_log(action: str, detail: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{_now()} | {action} | {detail}\n")


def _load_voice() -> str:
    """Load brand voice guide, stripping YAML header."""
    raw = _read(VOICE_PATH)
    if not raw:
        return ("Builder talking to builders. Short sentences. Active voice. "
                "Say what it does. No hype. 0 hashtags preferred, 1 max.")
    lines = raw.splitlines()
    body = [ln for ln in lines
            if not ln.startswith("title:") and not ln.startswith("updated:")]
    return "\n".join(body).strip()


def _load_recent_posts(n: int = 5) -> str:
    """Load the N most recent posted tweets for context."""
    if not POSTS_DIR.exists():
        return ""
    files = sorted(POSTS_DIR.glob("*.md"), reverse=True)[:n]
    posts = []
    for f in files:
        raw = _read(f)
        # Extract just the tweet text (skip metadata lines)
        lines = [ln for ln in raw.splitlines()
                 if ln.strip() and not ln.startswith("title:")
                 and not ln.startswith("updated:")
                 and not ln.startswith("posted:")
                 and not ln.startswith("tweet_id:")
                 and not ln.startswith("#")]
        if lines:
            posts.append(lines[0])
    return "\n".join(posts)


def _load_topic(intention: str) -> str:
    """Find a matching topic page if one exists."""
    if not TOPICS_DIR.exists():
        return ""
    slug = re.sub(r"[^a-z0-9]+", "-", intention.lower()).strip("-")[:40]
    for f in TOPICS_DIR.glob("*.md"):
        if slug[:12] in f.stem:
            return _read(f)
    return ""


def _rebuild_index() -> None:
    """Regenerate wiki/index.md from current directory contents."""
    lines = [
        "title: Wiki Index",
        f"updated: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "# OpenClay Wiki",
        "",
        "Auto-generated catalog of all wiki pages.",
        "",
        "## Brand",
    ]
    for f in sorted((WIKI_DIR / "brand").glob("*.md")):
        lines.append(f"- [{f.name}](brand/{f.name})")

    lines.append("\n## Posts")
    post_files = sorted(POSTS_DIR.glob("*.md"), reverse=True)[:20]
    if post_files:
        for f in post_files:
            lines.append(f"- [{f.stem}](posts/{f.name})")
    else:
        lines.append("_No posts yet._")

    lines.append("\n## Topics")
    topic_files = sorted(TOPICS_DIR.glob("*.md"))
    if topic_files:
        for f in topic_files:
            lines.append(f"- [{f.stem}](topics/{f.name})")
    else:
        lines.append("_No topics yet._")

    lines.append("\n## Sources")
    source_files = sorted(SOURCES_DIR.glob("*.md"))
    if source_files:
        for f in source_files:
            lines.append(f"- [{f.stem}](sources/{f.name})")
    else:
        lines.append("_No sources yet._")

    INDEX_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─── Public API ───

def build_tweet_prompt(intention: str) -> str:
    """Build a grounded tweet prompt from wiki memory.

    Combines: brand voice + recent posts (avoid repetition) + topic context.
    Returns a complete system+user prompt string for the LLM.
    """
    voice = _load_voice()
    recent = _load_recent_posts(5)
    topic_ctx = _load_topic(intention)

    parts = ["VOICE:\n" + voice]
    if recent:
        parts.append("ALREADY POSTED (don't repeat these):\n" + recent)
    if topic_ctx:
        parts.append("TOPIC:\n" + topic_ctx)
    parts.append(
        "---\n\n"
        f"Intention: {intention}\n\n"
        "Write one tweet. Under 280 chars.\n"
        "You are a builder who shipped something real. Talk like it.\n"
        "Short sentences. Active voice. State what it does or did.\n"
        "0 hashtags preferred. 1 max. Never 2.\n"
        "No hype words. No questions. No 'check it out'. No preamble.\n"
        "Use only real facts from the voice guide above.\n"
        "Output the tweet text and absolutely nothing else.\n"
    )
    return "\n\n".join(parts)


def log_posted_tweet(text: str, tweet_id: str = "") -> Path:
    """Log a posted tweet to wiki/posts/ and wiki/log.md.

    Returns the path to the created post file.
    """
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = _today_slug()
    post_path = POSTS_DIR / f"{slug}.md"

    content = (
        f"title: Tweet {slug}\n"
        f"posted: {_now()}\n"
        f"tweet_id: {tweet_id}\n\n"
        f"{text}\n"
    )
    post_path.write_text(content, encoding="utf-8")

    _append_log("post", f"Tweet posted → posts/{slug}.md")
    _rebuild_index()
    return post_path


def build_ingest_prompt(title: str, content: str) -> str:
    """Build a prompt to process a source into a wiki topic page.

    The LLM should extract key facts and write a structured wiki page.
    """
    voice = _load_voice()
    return (
        f"BRAND VOICE GUIDE:\n{voice}\n\n"
        "---\n\n"
        f"SOURCE TITLE: {title}\n\n"
        f"SOURCE CONTENT:\n{content[:3000]}\n\n"
        "---\n\n"
        "Extract the key facts from this source relevant to OpenClay.\n"
        "Write a structured wiki page in markdown with:\n"
        "- title: line at top\n"
        "- updated: date line\n"
        "- 2-4 key facts as bullet points\n"
        "- A one-sentence summary\n"
        "Output ONLY the markdown page. No commentary.\n"
    )


def ingest_source(title: str, content: str, page_text: str) -> Path:
    """Save a processed source to wiki/sources/ and its topic page."""
    SOURCES_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40]

    src_path = SOURCES_DIR / f"{slug}.md"
    src_path.write_text(
        f"title: {title}\n"
        f"updated: {datetime.now().strftime('%Y-%m-%d')}\n\n"
        f"{content[:5000]}\n",
        encoding="utf-8",
    )

    if page_text.strip():
        TOPICS_DIR.mkdir(parents=True, exist_ok=True)
        topic_path = TOPICS_DIR / f"{slug}.md"
        topic_path.write_text(page_text, encoding="utf-8")
        _append_log("ingest", f"Source + topic → {slug}.md")
    else:
        _append_log("ingest", f"Source only → sources/{slug}.md")

    _rebuild_index()
    return src_path


def build_lint_prompt() -> str:
    """Build a prompt to health-check the wiki.

    The LLM reviews index, log, and recent posts for consistency.
    """
    index = _read(INDEX_PATH)
    log_tail = "\n".join(_read(LOG_PATH).splitlines()[-20:])
    recent = _load_recent_posts(10)
    voice = _load_voice()

    return (
        "WIKI HEALTH CHECK\n\n"
        f"INDEX:\n{index}\n\n"
        f"RECENT LOG:\n{log_tail}\n\n"
        f"RECENT POSTS:\n{recent}\n\n"
        f"VOICE GUIDE:\n{voice}\n\n"
        "---\n\n"
        "Review the wiki for:\n"
        "1. Are recent tweets consistent with the voice guide?\n"
        "2. Any repeated or contradictory content?\n"
        "3. Are there topics that should be created from patterns in posts?\n"
        "4. Is the index up to date?\n\n"
        "Output a short report with specific issues and suggestions.\n"
        "No generic praise. Only actionable findings.\n"
    )
