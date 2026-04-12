"""audit_log.py — Audit trail for leadership visibility.

Every agent run appends ONE line to AUDIT_LOG.md with metadata only.
NEVER logs file contents — filename only.
Monthly auto-archive to AUDIT_LOG_[month].md.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
AUDIT_LOG_PATH = BASE_DIR / "AUDIT_LOG.md"


def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M")
def _month(): return datetime.now().strftime("%Y-%m")


def _ensure_header():
    """Create AUDIT_LOG.md with header if it doesn't exist."""
    if not AUDIT_LOG_PATH.exists():
        AUDIT_LOG_PATH.write_text(
            "# OpenClay Audit Log\n\n"
            "_One line per agent run. Never logs file contents._\n\n"
            "| Timestamp | Agent | File | Model | Output | Confidence |\n"
            "|-----------|-------|------|-------|--------|------------|\n",
            encoding="utf-8"
        )


def log_run(agent_name: str, input_file: str = "", model: str = "",
            output_file: str = "", confidence: str = "HIGH"):
    """Append one audit line. Only filenames — never contents."""
    _check_monthly_archive()
    _ensure_header()
    # Strip paths to filenames only for privacy
    in_name = Path(input_file).name if input_file else "—"
    out_name = Path(output_file).name if output_file else "—"
    model_name = model or "local"
    line = f"| {_now()} | {agent_name} | {in_name} | {model_name} | {out_name} | {confidence} |\n"
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)


def _check_monthly_archive():
    """Archive current log if it's from a previous month."""
    if not AUDIT_LOG_PATH.exists():
        return
    text = AUDIT_LOG_PATH.read_text(encoding="utf-8")
    lines = text.strip().splitlines()
    # Find first data line to check its month
    for line in lines:
        if line.startswith("| 20"):  # date line like "| 2026-04-10..."
            log_month = line.split("|")[1].strip()[:7]  # "2026-04"
            if log_month != _month():
                # Archive to AUDIT_LOG_2026-04.md
                archive = BASE_DIR / f"AUDIT_LOG_{log_month}.md"
                archive.write_text(text, encoding="utf-8")
                AUDIT_LOG_PATH.unlink()
            break


def read_log(last_n: int = 50) -> str:
    """Read last N entries from audit log."""
    if not AUDIT_LOG_PATH.exists():
        return "No audit log entries yet."
    text = AUDIT_LOG_PATH.read_text(encoding="utf-8")
    lines = text.strip().splitlines()
    # Header is first 5 lines, data is the rest
    header = lines[:5]
    data = lines[5:]
    if last_n and len(data) > last_n:
        data = data[-last_n:]
    return "\n".join(header + data)


def count_runs(agent_name: str = "") -> int:
    """Count total runs, optionally filtered by agent name."""
    if not AUDIT_LOG_PATH.exists():
        return 0
    text = AUDIT_LOG_PATH.read_text(encoding="utf-8")
    count = 0
    for line in text.splitlines():
        if line.startswith("| 20"):
            if not agent_name or agent_name.lower() in line.lower():
                count += 1
    return count


def summary() -> dict:
    """Summary stats for leadership dashboard."""
    if not AUDIT_LOG_PATH.exists():
        return {"total_runs": 0, "agents": {}, "period": _month()}
    text = AUDIT_LOG_PATH.read_text(encoding="utf-8")
    agents = {}
    total = 0
    for line in text.splitlines():
        if line.startswith("| 20"):
            total += 1
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                agent = parts[2]
                agents[agent] = agents.get(agent, 0) + 1
    return {"total_runs": total, "agents": agents, "period": _month()}


# ── Self test ───────────────────────────────────────────────────────

def self_test() -> bool:
    """Verify audit logging creates entries and reads them back."""
    # Log a test run
    log_run("self_test_agent", "test_input.txt", "local-test",
            "TEST_OUTPUT.md", "HIGH")
    # Verify log exists and contains entry
    assert AUDIT_LOG_PATH.exists(), "audit log not created"
    text = AUDIT_LOG_PATH.read_text()
    assert "self_test_agent" in text, "test entry not found"
    assert "test_input.txt" in text, "input filename not logged"
    assert "TEST_OUTPUT.md" in text, "output filename not logged"
    # Read log
    log_text = read_log(10)
    assert "self_test_agent" in log_text, "read_log failed"
    # Count
    c = count_runs("self_test_agent")
    assert c >= 1, f"count_runs returned {c}"
    # Summary
    s = summary()
    assert s["total_runs"] >= 1, "summary total wrong"
    assert "self_test_agent" in s["agents"], "summary missing agent"
    assert "period" in s, "summary missing period"
    # Clean up test entry (remove last line that contains self_test_agent)
    lines = AUDIT_LOG_PATH.read_text().splitlines()
    cleaned = [l for l in lines if "self_test_agent" not in l]
    AUDIT_LOG_PATH.write_text("\n".join(cleaned) + "\n", encoding="utf-8")
    return True


if __name__ == "__main__":
    print("self_test:", self_test())
