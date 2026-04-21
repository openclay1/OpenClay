"""
memory_dreaming.py — OpenClay Dreaming System
COANA Labs · San Juan, Puerto Rico

Three-phase background memory consolidation: Light → REM → Deep.
Runs after each conversation turn (5-minute cooldown).
Never blocks inference. Fully local — no network calls.

Architecture (memsearch pattern):
  MEMORY.md  = source of truth (human-readable, editable, version-controlled)
  ChromaDB   = shadow index rebuilt from MEMORY.md on demand
  DREAMS.md  = human-readable summary of each cycle

Usage:
    import memory_dreaming
    memory_dreaming.configure(base_dir, conv_dir, ollama_url, model)
    memory_dreaming.sync_memory_md_on_startup()        # in main()
    memory_dreaming.trigger_dreaming()                 # in _save_conversation_turn()
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Module state (set by configure()) ────────────────────────────
_base_dir: Path | None = None
_conv_dir: Path | None = None
_ollama_url: str = "http://localhost:11434"
_model: str = "qwen2.5:3b-instruct-q4_K_M"
_chroma_client: Any = None   # optional — if None, ChromaDB sync is skipped

_last_cycle_time: float = 0.0
COOLDOWN_SECONDS = 300          # 5 minutes between cycles
MIN_SCORE       = 0.55          # promote if composite ≥ this
MAX_PROMOTE     = 8             # cap memories promoted per cycle
LLM_TIMEOUT     = 90            # seconds — generous for slow CPUs
_lock           = threading.Lock()
_running        = False


# ── Public API ───────────────────────────────────────────────────

def configure(
    base_dir: Path,
    conv_dir: Path,
    ollama_url: str = "http://localhost:11434",
    model: str = "qwen2.5:3b-instruct-q4_K_M",
    chroma_client: Any = None,
) -> None:
    """Call once from main() before the HTTP server starts."""
    global _base_dir, _conv_dir, _ollama_url, _model, _chroma_client
    _base_dir    = Path(base_dir)
    _conv_dir    = Path(conv_dir)
    _ollama_url  = ollama_url
    _model       = model
    _chroma_client = chroma_client
    # Ensure output files exist
    _memory_md().parent.mkdir(parents=True, exist_ok=True)
    _dreams_md().parent.mkdir(parents=True, exist_ok=True)
    if not _memory_md().exists():
        _memory_md().write_text(
            "# OpenClay Memory\n\nThis file is the source of truth for what OpenClay "
            "knows about you.\nIt is updated automatically after each session by the "
            "Dreaming system.\nYou can edit it freely — the system respects your edits.\n\n",
            encoding="utf-8",
        )
    print("  [Dreaming] module ready")


def trigger_dreaming() -> None:
    """
    Called from _save_conversation_turn() after each user↔Clay exchange.
    Spawns a daemon thread to run the dreaming cycle if cooldown has elapsed.
    Never raises — failure is logged, not propagated.
    """
    global _last_cycle_time, _running
    if _base_dir is None:
        return  # not configured yet
    now = time.monotonic()
    with _lock:
        if _running:
            return
        if now - _last_cycle_time < COOLDOWN_SECONDS:
            return
        _running = True
        _last_cycle_time = now
    t = threading.Thread(
        target=_safe_run_cycle,
        daemon=True,
        name="dreaming-cycle",
    )
    t.start()


def sync_memory_md_on_startup() -> None:
    """
    Rebuild ChromaDB shadow index from MEMORY.md in a background thread.
    Call once from main() after configure().
    """
    if _base_dir is None:
        return
    t = threading.Thread(
        target=_sync_memory_md_to_chromadb,
        args=(True,),   # startup=True → quiet mode
        daemon=True,
        name="dreaming-startup-sync",
    )
    t.start()


# ── Paths ─────────────────────────────────────────────────────────

def _memory_md() -> Path:
    return _base_dir / "MEMORY.md"


def _dreams_md() -> Path:
    return _base_dir / "DREAMS.md"


# ── Cycle orchestration ──────────────────────────────────────────

def _safe_run_cycle() -> None:
    global _running
    try:
        run_dreaming_cycle()
    except Exception as exc:
        print(f"  [Dreaming] cycle error: {exc}")
    finally:
        with _lock:
            _running = False


def run_dreaming_cycle() -> None:
    """
    Light → REM → Deep.

    Light : extract candidate sentences from today's conversation logs.
    REM   : LLM classifies and scores each candidate.
    Deep  : top candidates promoted to MEMORY.md + DREAMS.md.
    """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"  [Dreaming] cycle started at {ts}")

    # ── Phase 1: Light — extract candidates ──────────────────────
    candidates = _extract_candidates()
    if not candidates:
        print("  [Dreaming] no candidates — skipping")
        return
    print(f"  [Dreaming] Light: {len(candidates)} candidates extracted")

    # ── Phase 2: REM — classify + score ──────────────────────────
    scored = _classify_and_score(candidates)
    promoted = [m for m in scored if m["composite"] >= MIN_SCORE]
    promoted.sort(key=lambda m: m["composite"], reverse=True)
    promoted = promoted[:MAX_PROMOTE]
    if not promoted:
        print("  [Dreaming] REM: no candidates passed threshold")
        return
    print(f"  [Dreaming] REM: {len(promoted)}/{len(scored)} passed threshold")

    # ── Phase 3: Deep — write to disk (no LLM) ───────────────────
    # Critical path: memory promotion + shadow sync happen immediately.
    _append_to_memory_md(promoted)
    _write_dreams_md(promoted)                # writes memory list; diary added later
    _sync_memory_md_to_chromadb()
    print(f"  [Dreaming] Deep: {len(promoted)} memories promoted → MEMORY.md + DREAMS.md")

    # Diary: fire-and-forget sub-thread — LLM call, does not block this cycle.
    # The daemon thread (and _running flag) clears before the diary finishes.
    _snapshot = list(promoted)
    threading.Thread(
        target=_diary_worker,
        args=(_snapshot,),
        daemon=True,
        name="dreaming-diary",
    ).start()


# ── Phase 1: Light ───────────────────────────────────────────────

def _extract_candidates() -> list[dict]:
    """
    Read all JSONL conversation files from today, extract assistant sentences,
    compute per-sentence frequency and recency signals.

    Returns list of dicts:
        {text, recency, frequency, unique_queries, source_file}
    """
    if _conv_dir is None:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    today_files = sorted(_conv_dir.glob(f"{today}-*.jsonl"))
    if not today_files:
        return []

    all_turns: list[dict] = []
    for path in today_files:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    all_turns.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass

    if not all_turns:
        return []

    # Split assistant turns into sentences; track which user prompts preceded each
    sentence_map: dict[str, dict] = {}  # sentence → {count, recency_ts, queries}
    total_turns = len(all_turns)

    for idx, turn in enumerate(all_turns):
        if turn.get("role") != "assistant":
            continue
        content = (turn.get("content") or "").strip()
        if not content:
            continue

        # Recency: fraction of the way through today's log (1.0 = most recent)
        recency = (idx + 1) / total_turns

        # Preceding user message (for query diversity)
        user_query = ""
        if idx > 0 and all_turns[idx - 1].get("role") == "user":
            user_query = (all_turns[idx - 1].get("content") or "")[:200]

        for sentence in _split_sentences(content):
            if len(sentence) < 30 or len(sentence) > 600:
                continue
            key = _normalize(sentence)
            if key not in sentence_map:
                sentence_map[key] = {
                    "text": sentence,
                    "count": 0,
                    "recency_sum": 0.0,
                    "queries": set(),
                }
            sentence_map[key]["count"] += 1
            sentence_map[key]["recency_sum"] += recency
            if user_query:
                sentence_map[key]["queries"].add(user_query[:80])

    candidates = []
    for key, data in sentence_map.items():
        count = data["count"]
        avg_recency = data["recency_sum"] / count
        unique_q = len(data["queries"])
        candidates.append({
            "text": data["text"],
            "frequency": min(count / 3.0, 1.0),      # normalize: 3 repeats → 1.0
            "recency": avg_recency,
            "unique_queries": min(unique_q / 3.0, 1.0),  # 3 distinct queries → 1.0
        })

    # Limit to 40 most frequent for REM phase (LLM calls are expensive on CPU)
    candidates.sort(key=lambda c: c["frequency"] + c["recency"], reverse=True)
    return candidates[:40]


def _split_sentences(text: str) -> list[str]:
    """Rough sentence splitter — handles most English/Spanish punctuation."""
    # Split on . ! ? followed by whitespace + capital (or end of string)
    parts = re.split(r'(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÜÑ"\'])', text)
    result = []
    for p in parts:
        p = p.strip()
        if p:
            result.append(p)
    return result or [text.strip()]


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace for deduplication key."""
    return re.sub(r'\s+', ' ', text.lower().strip())


# ── Phase 2: REM ─────────────────────────────────────────────────

# Six scoring signal weights (adapted from OpenClaw Dreaming)
_WEIGHTS = {
    "relevance":   0.30,
    "frequency":   0.24,
    "query_div":   0.15,
    "recency":     0.15,
    "consolidation": 0.10,
    "richness":    0.06,
}


def _classify_and_score(candidates: list[dict]) -> list[dict]:
    """
    Ask the local LLM to classify each candidate and estimate relevance + richness.
    Combine LLM outputs with pre-computed signals into a composite score.
    """
    scored = []
    # We batch 10 candidates per LLM call to reduce round-trips
    batch_size = 10
    batches = [candidates[i:i + batch_size] for i in range(0, len(candidates), batch_size)]

    for batch in batches:
        # Build prompt
        items_text = ""
        for i, c in enumerate(batch):
            items_text += f"{i + 1}. {c['text']}\n"

        prompt = f"""\
You are a memory classifier for a personal AI assistant. Analyze the following statements
and return a JSON array. For each statement return exactly:
  {{"type": "<factual|experiential|belief|preference|skill>",
   "relevance": <0.0-1.0>,
   "richness": <0.0-1.0>,
   "summary": "<15 words max>"}}

- relevance: how personally meaningful is this for long-term memory? (0=generic, 1=specific/personal)
- richness: how much conceptual depth does it carry? (0=trivial, 1=multi-concept insight)

Statements:
{items_text}
Return ONLY the JSON array, no markdown, no explanation."""

        raw = _llm(prompt, system="You are a precise JSON classifier. Return only valid JSON arrays.")
        llm_results = _parse_llm_json(raw, len(batch))

        for c, llm in zip(batch, llm_results):
            relevance  = float(llm.get("relevance", 0.4))
            richness   = float(llm.get("richness", 0.3))

            # Consolidation signal: does this appear in MEMORY.md already?
            existing_text = _memory_md().read_text(encoding="utf-8") if _memory_md().exists() else ""
            snippet = c["text"][:60].lower()
            consolidation = 0.0 if snippet in existing_text.lower() else 1.0

            composite = (
                relevance            * _WEIGHTS["relevance"]
                + c["frequency"]     * _WEIGHTS["frequency"]
                + c["unique_queries"] * _WEIGHTS["query_div"]
                + c["recency"]       * _WEIGHTS["recency"]
                + consolidation      * _WEIGHTS["consolidation"]
                + richness           * _WEIGHTS["richness"]
            )

            scored.append({
                "text":          c["text"],
                "type":          llm.get("type", "factual"),
                "summary":       llm.get("summary", c["text"][:60]),
                "relevance":     relevance,
                "richness":      richness,
                "frequency":     c["frequency"],
                "recency":       c["recency"],
                "unique_queries": c["unique_queries"],
                "consolidation": consolidation,
                "composite":     round(composite, 3),
            })

    return scored


def _parse_llm_json(raw: str, expected_count: int) -> list[dict]:
    """
    Try to parse LLM response as JSON array.
    Falls back to safe defaults if parsing fails.
    """
    # Strip markdown fences
    text = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip().strip("`")
    # Find first [...] block
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            results = json.loads(m.group(0))
            if isinstance(results, list):
                # Pad or trim to expected_count
                while len(results) < expected_count:
                    results.append({})
                return results[:expected_count]
        except json.JSONDecodeError:
            pass
    # Fallback: safe defaults
    return [{"type": "factual", "relevance": 0.35, "richness": 0.3, "summary": ""}
            for _ in range(expected_count)]


# ── Phase 3: Deep ────────────────────────────────────────────────

def _append_to_memory_md(promoted: list[dict]) -> None:
    """
    Append promoted memories to MEMORY.md, grouped by type.
    memsearch pattern: MEMORY.md is always source of truth.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    by_type: dict[str, list[dict]] = {}
    for m in promoted:
        by_type.setdefault(m["type"], []).append(m)

    lines = [f"\n## Session — {now}\n"]
    type_labels = {
        "factual":      "Factual",
        "experiential": "Experiential",
        "belief":       "Belief / Perspective",
        "preference":   "Preference",
        "skill":        "Skill / Capability",
    }
    for mem_type, mems in sorted(by_type.items()):
        label = type_labels.get(mem_type, mem_type.title())
        lines.append(f"### {label}\n")
        for m in mems:
            score_str = f"[score: {m['composite']:.2f}]"
            lines.append(f"- {m['text']} {score_str}\n")
        lines.append("\n")

    block = "".join(lines)
    with open(_memory_md(), "a", encoding="utf-8") as f:
        f.write(block)


def _generate_dream_diary(promoted: list[dict]) -> str:
    """
    Ask the LLM to write a brief narrative reflection on what was learned.
    Returns the diary string. Fails gracefully → returns empty string.
    Called only from _diary_worker (fire-and-forget thread), never on the main cycle.
    """
    if not promoted:
        return ""

    bullet_list = "\n".join(f"- {m['summary'] or m['text'][:80]}" for m in promoted)
    prompt = f"""\
You are the memory system of a personal AI assistant called Clay. After each session you
write a brief internal diary entry — 3-5 sentences — reflecting on what you learned about
the user today. Write in first person as Clay. Be specific, warm, and concise.

What was learned this session:
{bullet_list}

Write the diary entry now (no heading, no quotes):"""

    return _llm(prompt, system="You write brief, warm diary entries as a personal AI assistant.", timeout=60)


def _diary_worker(promoted: list[dict]) -> None:
    """
    Fire-and-forget: generate a narrative diary entry and patch DREAMS.md.
    Runs in its own daemon thread — the main dreaming cycle has already cleared
    by the time this starts. Failure here is logged and ignored.
    """
    try:
        diary = _generate_dream_diary(promoted)
        if diary:
            _patch_dreams_md_diary(diary)
    except Exception as exc:
        print(f"  [Dreaming] diary error: {exc}")


def _patch_dreams_md_diary(diary: str) -> None:
    """
    Insert the diary paragraph into the most recent entry in DREAMS.md.
    Finds the first '## YYYY-MM-DD HH:MM' heading and inserts after it.
    No-ops gracefully if the file has changed or the pattern isn't found.
    """
    if not _dreams_md().exists() or not diary:
        return
    try:
        text = _dreams_md().read_text(encoding="utf-8")
        # Match the first session heading (newest entry is always first)
        pattern = r'(## \d{4}-\d{2}-\d{2} \d{2}:\d{2}\n\n)'
        replacement = r'\1' + diary.strip() + '\n\n'
        patched, n = re.subn(pattern, replacement, text, count=1)
        if n:
            _dreams_md().write_text(patched, encoding="utf-8")
            print("  [Dreaming] diary added to DREAMS.md")
    except Exception as exc:
        print(f"  [Dreaming] diary patch error: {exc}")


def _write_dreams_md(promoted: list[dict]) -> None:
    """
    Prepend a new entry to DREAMS.md (newest first).
    Writes the memory list immediately — no LLM calls.
    The diary paragraph is patched in later by _diary_worker.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing = ""
    if _dreams_md().exists():
        existing = _dreams_md().read_text(encoding="utf-8")
        # Strip the header if present so we can re-add it
        existing = re.sub(r'^# OpenClay Dreams.*?\n\n', '', existing, flags=re.DOTALL).lstrip()

    lines = [
        "# OpenClay Dreams\n",
        "*What Clay learned — newest first.*\n\n",
        "---\n\n",
        f"## {now}\n\n",
        # Diary paragraph inserted here by _patch_dreams_md_diary when ready
        "**Memories promoted this cycle:**\n\n",
    ]
    for m in promoted:
        tag = m["type"]
        score = m["composite"]
        lines.append(f"- `{tag}` [{score:.2f}] {m['text'][:120]}\n")
    lines.append("\n---\n\n")

    if existing:
        lines.append(existing)

    _dreams_md().write_text("".join(lines), encoding="utf-8")


def _sync_memory_md_to_chromadb(startup: bool = False) -> None:
    """
    Parse MEMORY.md and upsert all bullet-point memories into ChromaDB.
    memsearch shadow-index pattern: ChromaDB is always rebuildable from MEMORY.md.
    Skips gracefully if ChromaDB is unavailable.
    """
    if _chroma_client is None:
        # Try to import chromadb directly as fallback
        try:
            import chromadb  # type: ignore
            client = chromadb.PersistentClient(path=str(_base_dir / "memory_store"))
        except Exception:
            if not startup:
                print("  [Dreaming] ChromaDB not available — shadow sync skipped")
            return
    else:
        client = _chroma_client

    if not _memory_md().exists():
        return

    try:
        collection = client.get_or_create_collection("openclay_dreams")
        text = _memory_md().read_text(encoding="utf-8")

        memories: list[tuple[str, str, str]] = []  # (id, text, section)
        current_section = "general"
        for line in text.splitlines():
            # Track section headings
            if line.startswith("## "):
                current_section = line[3:].strip()
            elif line.startswith("- ") and "[score:" in line:
                # Strip the score annotation for the stored text
                mem_text = re.sub(r'\[score: [\d.]+\]', '', line[2:]).strip()
                if len(mem_text) >= 20:
                    mem_id = "dream-" + _stable_id(mem_text)
                    memories.append((mem_id, mem_text, current_section))

        if not memories:
            return

        # Upsert in batches of 50
        batch_size = 50
        for i in range(0, len(memories), batch_size):
            batch = memories[i:i + batch_size]
            ids       = [m[0] for m in batch]
            docs      = [m[1] for m in batch]
            metas     = [{"section": m[2], "source": "MEMORY.md"} for m in batch]
            collection.upsert(ids=ids, documents=docs, metadatas=metas)

        if not startup:
            print(f"  [Dreaming] ChromaDB synced: {len(memories)} memories")
    except Exception as exc:
        if not startup:
            print(f"  [Dreaming] ChromaDB sync error: {exc}")


def _stable_id(text: str) -> str:
    """Deterministic short ID from text content."""
    import hashlib
    return hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:16]


# ── LLM call ────────────────────────────────────────────────────

def _llm(prompt: str, system: str = "", timeout: int = LLM_TIMEOUT) -> str:
    """
    Non-streaming Ollama call. Returns response text or empty string on failure.
    Always local — never calls any external URL.
    """
    payload: dict[str, Any] = {
        "model":  _model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 512,
        },
    }
    if system:
        payload["system"] = system

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{_ollama_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            obj = json.loads(body)
            return (obj.get("response") or "").strip()
    except Exception as exc:
        print(f"  [Dreaming] LLM call failed: {exc}")
        return ""
