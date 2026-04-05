"""wiki_engine.py — Karpathy-style LLM wiki engine for OpenClay."""
from __future__ import annotations
import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
WIKI_DIR = BASE_DIR / "wiki"
RAW_DIR = BASE_DIR / "raw"
VOICE_PATH = WIKI_DIR / "brand" / "voice.md"
LOG_PATH = WIKI_DIR / "log.md"
INDEX_PATH = WIKI_DIR / "index.md"
OVERVIEW_PATH = WIKI_DIR / "overview.md"
POSTS_DIR = WIKI_DIR / "posts"
TOPICS_DIR = WIKI_DIR / "topics"
SOURCES_DIR = WIKI_DIR / "sources"
CONCEPTS_DIR = WIKI_DIR / "concepts"
ENTITIES_DIR = WIKI_DIR / "entities"
COMPARISONS_DIR = WIKI_DIR / "comparisons"
_WIKI_SUBS = [WIKI_DIR / "brand", POSTS_DIR, TOPICS_DIR, SOURCES_DIR,
              CONCEPTS_DIR, ENTITIES_DIR, COMPARISONS_DIR]
_RAW_SUBS = [RAW_DIR / "articles", RAW_DIR / "assets"]
_TEXT_EXTS = {".md", ".txt", ".html", ".json", ".csv", ".py", ".js", ".ts"}

def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _today(): return datetime.now().strftime("%Y-%m-%d")
def _slug(t): return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:50]
def _read(p): return p.read_text(encoding="utf-8") if p.exists() else ""
def _scan(d): return sorted(d.glob("*.md")) if d.exists() else []

def _append_log(action: str, detail: str):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{_now()} | {action} | {detail}\n")

def _load_voice() -> str:
    raw = _read(VOICE_PATH)
    if not raw:
        return ("Builder talking to builders. Short sentences. Active voice. "
                "Say what it does. No hype. 0 hashtags preferred, 1 max.")
    return "\n".join(ln for ln in raw.splitlines()
                     if not ln.startswith(("title:", "updated:"))).strip()

def _load_recent_posts(n: int = 5) -> str:
    if not POSTS_DIR.exists(): return ""
    posts = []
    for f in sorted(POSTS_DIR.glob("*.md"), reverse=True)[:n]:
        lines = [ln for ln in _read(f).splitlines()
                 if ln.strip() and not ln.startswith(
                     ("title:", "updated:", "posted:", "tweet_id:", "#", "---"))]
        if lines: posts.append(lines[0])
    return "\n".join(posts)

# ─── Index ───

def rebuild_index():
    lines = [f"---\ntitle: Wiki Index\nupdated: {_today()}\n---\n",
             "# Wiki Index\n", "Auto-generated catalog.\n"]
    for name, files in [
        ("Concepts", _scan(CONCEPTS_DIR)), ("Entities", _scan(ENTITIES_DIR)),
        ("Sources", _scan(SOURCES_DIR)), ("Comparisons", _scan(COMPARISONS_DIR)),
        ("Topics", _scan(TOPICS_DIR)), ("Posts", _scan(POSTS_DIR)[-20:]),
    ]:
        lines.append(f"## {name}")
        for f in (files or []):
            lines.append(f"- [{f.stem}]({f.relative_to(WIKI_DIR)})")
        if not files: lines.append(f"_No {name.lower()} yet._")
        lines.append("")
    INDEX_PATH.write_text("\n".join(lines), encoding="utf-8")

# ─── Init ───

def wiki_init() -> str:
    for d in _WIKI_SUBS + _RAW_SUBS + [RAW_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    rebuild_index()
    _append_log("init", "Wiki structure created")
    return "Wiki initialized. Drop files in raw/ to ingest them."

# ─── Ingest ───

def find_raw_file(filename: str) -> Path | None:
    if not RAW_DIR.exists(): return None
    slug = filename.lower().strip()
    for f in RAW_DIR.rglob("*"):
        if f.is_file() and (slug in f.name.lower() or slug in f.stem.lower()):
            return f
    return None

def build_ingest_prompt(filepath: Path) -> str:
    content = (_read(filepath) if filepath.suffix in _TEXT_EXTS
               else f"[Binary file: {filepath.name}, {filepath.stat().st_size}b]")
    concepts = ", ".join(f.stem for f in _scan(CONCEPTS_DIR)[:20]) or "none"
    entities = ", ".join(f.stem for f in _scan(ENTITIES_DIR)[:20]) or "none"
    return (
        "You are a wiki engine. Process this source into structured pages.\n\n"
        f"SOURCE: {filepath.name}\nCONTENT:\n{content[:4000]}\n\n---\n\n"
        f"EXISTING CONCEPTS: {concepts}\nEXISTING ENTITIES: {entities}\n\n"
        "Write your response in EXACTLY this format:\n"
        "===SOURCE===\n[summary with YAML frontmatter]\n"
        "===CONCEPT: name===\n[concept page]\n"
        "===ENTITY: name===\n[entity page]\n"
        "===COMPARISON: name===\n[comparison page]\n\n"
        "YAML frontmatter: title, type, sources, related, created, updated, "
        f"confidence. Today: {_today()}.\nOnly output structured pages.\n"
    )

def save_ingest_result(filepath: Path, llm_output: str) -> list[str]:
    """Parse LLM ingest output, save to wiki. Returns created paths."""
    created, source_slug = [], _slug(filepath.stem)
    sections = re.split(r"===(\w+)(?::\s*(.+?))?===", llm_output)
    i = 1
    while i + 2 < len(sections):
        stype, sname, scontent = (sections[i].strip().upper(),
                                  (sections[i+1] or "").strip(), sections[i+2].strip())
        i += 3
        if not scontent: continue
        dirmap = {"SOURCE": SOURCES_DIR, "CONCEPT": CONCEPTS_DIR,
                  "ENTITY": ENTITIES_DIR, "COMPARISON": COMPARISONS_DIR}
        target_dir = dirmap.get(stype)
        if not target_dir: continue
        slug = _slug(sname) if sname else source_slug
        if stype == "COMPARISON": slug = f"cmp-{slug}" if sname else f"cmp-{source_slug}"
        target_dir.mkdir(parents=True, exist_ok=True)
        p = target_dir / f"{slug}.md"
        if p.exists() and stype in ("CONCEPT", "ENTITY"):
            scontent = _read(p).rstrip() + "\n\n---\n\n" + scontent
        p.write_text(scontent + "\n", encoding="utf-8")
        created.append(f"{target_dir.name}/{slug}.md")
    if not created and llm_output.strip():
        SOURCES_DIR.mkdir(parents=True, exist_ok=True)
        p = SOURCES_DIR / f"{source_slug}.md"
        p.write_text(llm_output.strip() + "\n", encoding="utf-8")
        created.append(f"sources/{source_slug}.md")
    for c in created:
        _append_log("ingest", f"Created {c} from {filepath.name}")
    rebuild_index()
    return created

# ─── Query ───

def build_query_prompt(question: str) -> str:
    index = _read(INDEX_PATH)
    overview = _read(OVERVIEW_PATH)[:500]
    q_words = [w for w in question.lower().split() if len(w) > 3]
    relevant = []
    for d in [CONCEPTS_DIR, ENTITIES_DIR, SOURCES_DIR, COMPARISONS_DIR, TOPICS_DIR]:
        for f in _scan(d):
            content = _read(f)
            if (question.lower() in content.lower() or
                    any(w in f.stem.lower() for w in q_words)):
                relevant.append(f"### {f.relative_to(WIKI_DIR)}\n{content[:600]}")
            if len(relevant) >= 8: break
    rel_text = "\n\n".join(relevant) or "_No matching pages._"
    return (
        "Answer using ONLY wiki pages below. Cite pages as [[name]].\n\n"
        f"INDEX:\n{index[:800]}\n\nOVERVIEW:\n{overview}\n\n"
        f"RELEVANT PAGES:\n{rel_text}\n\n---\n\nQUESTION: {question}\n\n"
        "If wiki lacks info, say so. If the answer merits a new page, "
        "suggest: 'File as concept: [title]'\n"
    )

# ─── Lint ───

def build_lint_prompt() -> str:
    index, log_tail = _read(INDEX_PATH), "\n".join(_read(LOG_PATH).splitlines()[-30:])
    stats = (f"{len(_scan(CONCEPTS_DIR))} concepts, {len(_scan(ENTITIES_DIR))} "
             f"entities, {len(_scan(SOURCES_DIR))} sources, "
             f"{len(_scan(POSTS_DIR))} posts")
    orphans = [str(f.relative_to(WIKI_DIR)) for d in [CONCEPTS_DIR, ENTITIES_DIR]
               for f in _scan(d) if "related:" not in _read(f)
               and "sources:" not in _read(f)]
    return (
        f"WIKI HEALTH CHECK\n\nStats: {stats}\n\n"
        f"INDEX:\n{index[:600]}\n\nRECENT LOG:\n{log_tail}\n\n"
        f"ORPHANS: {', '.join(orphans) or 'none'}\n\n---\n\n"
        "Find: 1) Orphan pages 2) Missing concepts 3) Contradictions "
        "4) Stale info 5) Unlinked connections.\n"
        "Short specific report. No praise. Actionable findings only.\n"
    )

# ─── Tweet ───

def build_tweet_prompt(intention: str) -> str:
    voice, recent = _load_voice(), _load_recent_posts(5)
    topic_ctx = ""
    slug = _slug(intention)[:12]
    for f in _scan(TOPICS_DIR):
        if slug in f.stem:
            topic_ctx = _read(f); break
    parts = ["VOICE:\n" + voice]
    if recent: parts.append("ALREADY POSTED (don't repeat):\n" + recent)
    if topic_ctx: parts.append("TOPIC:\n" + topic_ctx)
    parts.append(
        "---\n\n" f"Intention: {intention}\n\n"
        "Write one tweet. Under 280 chars.\n"
        "Builder voice. Short sentences. Active voice.\n"
        "0 hashtags preferred. 1 max. Never 2. No hype. No questions.\n"
        "Use only real facts from the voice guide.\n"
        "Last thing in every tweet: github.com/openclay1/OpenClay\n"
        "Output tweet text only.\n")
    return "\n\n".join(parts)

def log_posted_tweet(text: str, tweet_id: str = "") -> Path:
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = datetime.now().strftime("%Y%m%d-%H%M%S")
    p = POSTS_DIR / f"{slug}.md"
    p.write_text(f"---\ntitle: Tweet {slug}\ntype: post\n"
                 f"posted: {_now()}\ntweet_id: {tweet_id}\n---\n\n{text}\n",
                 encoding="utf-8")
    _append_log("post", f"Tweet posted -> posts/{slug}.md")
    rebuild_index()
    return p
