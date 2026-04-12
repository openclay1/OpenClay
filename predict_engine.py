"""predict_engine.py — Lightweight next-action suggestions for OpenClay.

Reads BRAIN.md + SESSION.md + DECISIONS.md to predict the 2-3 actions
the user is most likely to need next, based on pattern matching.

No ML models. No embeddings. Plain text pattern matching only.
Each suggestion is under 50 words.
"""
from __future__ import annotations

import re
from pathlib import Path

BASE_DIR = Path(__file__).parent

# ── Task patterns → likely follow-ups ────────────────────────────────

_FOLLOW_UPS: list[tuple[list[str], list[str]]] = [
    # (trigger keywords in recent tasks, suggested next actions)
    (
        ["ingest", "document", "file", "pdf", "raw"],
        [
            "Review wiki index for new pages created by ingest",
            "Run wiki lint to check for orphan pages or missing links",
            "Summarize the ingested content into a topic page",
        ],
    ),
    (
        ["clean", "storage", "disk", "rotate", "log"],
        [
            "Run self_tests to verify nothing broke during cleanup",
            "Check healing_log.md for any new warnings",
            "Review queue/ folder for stale pending tasks",
        ],
    ),
    (
        ["test", "self_test", "selftest", "fix", "bug", "error"],
        [
            "Commit the fix and update CHANGELOG.md",
            "Check healing_log.md for related past failures",
            "Run the full self_test suite to catch regressions",
        ],
    ),
    (
        ["summarize", "summary", "report", "folder"],
        [
            "Save the summary as a wiki concept page",
            "Share the summary via mobile bridge",
            "Identify action items from the summary",
        ],
    ),
    (
        ["plan", "today", "schedule", "organize"],
        [
            "Start with the highest-priority task from the plan",
            "Set a reminder to review progress at end of day",
            "Break the first task into smaller steps",
        ],
    ),
    (
        ["wiki", "concept", "entity", "knowledge"],
        [
            "Run wiki lint to find orphan or contradictory pages",
            "Check if related concepts should be linked",
            "Update the wiki overview page",
        ],
    ),
    (
        ["build", "self_build", "improve", "deploy"],
        [
            "Run all self_tests to verify the build",
            "Review self_build_log.md for pass/fail trends",
            "Check module line counts — keep every file under 300 lines",
        ],
    ),
    (
        ["compress", "brain", "memory", "session"],
        [
            "Read BRAIN.md to verify compression kept useful facts",
            "Clear stale entries from DECISIONS.md",
            "Check that BRAIN.md is still under 500 words",
        ],
    ),
    (
        ["paper", "biotech", "literature", "review", "abstract",
         "clinical", "trial", "ingest"],
        [
            "Write a hypothesis based on the gap analysis",
            "Update protocol document with new findings",
            "Search for studies that contradict current conclusions",
        ],
    ),
]

# Fallback when no patterns match
_DEFAULT_SUGGESTIONS = [
    "Check healing_log.md for any warnings or failures",
    "Run self_tests to verify system health",
    "Review queue/ for pending tasks",
]


# ── Core engine ──────────────────────────────────────────────────────

def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _extract_recent_tasks(session: str, brain: str) -> list[str]:
    """Pull task names from SESSION.md and recent BRAIN.md entries."""
    lines = []
    for text in (session, brain):
        for line in text.splitlines():
            # Match lines like "- [2026-04-09 10:23] task_name → outcome"
            m = re.match(r"^-\s*\[.*?\]\s*(.+?)(?:\s*→.*)?$", line.strip())
            if m:
                lines.append(m.group(1).strip().lower())
    return lines[-15:]  # last 15 tasks max


def _score_pattern(triggers: list[str], recent: list[str]) -> int:
    """Count how many trigger keywords appear in recent task history."""
    combined = " ".join(recent)
    return sum(1 for t in triggers if t in combined)


def predict(query: str = "") -> list[str]:
    """Return 2-3 suggested next actions based on current context.

    Each suggestion is plain text, under 50 words.
    """
    session = _read(BASE_DIR / "SESSION.md")
    brain = _read(BASE_DIR / "BRAIN.md")
    decisions = _read(BASE_DIR / "DECISIONS.md")

    recent = _extract_recent_tasks(session, brain)

    # Also include the current query as context
    if query:
        recent.append(query.lower())

    # Score each pattern group
    scored: list[tuple[int, list[str]]] = []
    for triggers, suggestions in _FOLLOW_UPS:
        score = _score_pattern(triggers, recent)
        if score > 0:
            scored.append((score, suggestions))

    # Also check decisions for recurring patterns
    if decisions:
        decision_words = decisions.lower()
        for triggers, suggestions in _FOLLOW_UPS:
            if any(t in decision_words for t in triggers):
                # Boost score for patterns that appear in past decisions
                for i, (s, sug) in enumerate(scored):
                    if sug == suggestions:
                        scored[i] = (s + 1, sug)

    if not scored:
        return _DEFAULT_SUGGESTIONS[:2]

    # Sort by score descending, pick top suggestions
    scored.sort(key=lambda x: x[0], reverse=True)

    results: list[str] = []
    for _, suggestions in scored:
        for s in suggestions:
            if s not in results:
                results.append(s)
            if len(results) >= 3:
                return results

    return results[:3] if results else _DEFAULT_SUGGESTIONS[:2]


def format_suggestions(suggestions: list[str]) -> str:
    """Format suggestions as a numbered list for display."""
    if not suggestions:
        return "No suggestions available."
    lines = [f"  {i+1}. {s}" for i, s in enumerate(suggestions)]
    return "Next steps:\n" + "\n".join(lines)


def predict_and_format(query: str = "") -> str:
    """One-call convenience: predict + format."""
    return format_suggestions(predict(query))


# ── Self test ────────────────────────────────────────────────────────

def self_test() -> bool:
    """Verify predict_engine produces valid suggestions."""
    # Basic prediction returns a list
    results = predict()
    assert isinstance(results, list), "predict must return list"
    assert 1 <= len(results) <= 3, f"expected 1-3 suggestions, got {len(results)}"

    # Each suggestion is under 50 words
    for s in results:
        assert isinstance(s, str), "suggestion must be string"
        assert len(s.split()) <= 50, f"suggestion over 50 words: {s}"

    # Query-based prediction
    results_q = predict("ingest a new document")
    assert len(results_q) >= 1, "query prediction returned nothing"
    # Should match ingest/document pattern
    combined = " ".join(results_q).lower()
    assert any(w in combined for w in ("wiki", "ingest", "lint", "summarize",
                                        "orphan", "topic", "review")), \
        f"ingest query didn't match expected patterns: {results_q}"

    # Format works
    formatted = format_suggestions(results_q)
    assert "Next steps:" in formatted, "format missing header"
    assert "1." in formatted, "format missing numbering"

    # predict_and_format convenience
    pf = predict_and_format("test")
    assert isinstance(pf, str) and len(pf) > 0, "predict_and_format failed"

    return True
