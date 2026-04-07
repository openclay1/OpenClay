"""self_improver.py — Autonomous improvement loop (runs every 24 h).

1. Collect failure data from healing_log.md, agent_decisions.md, SQLite
2. Identify top 3 failure patterns in last 7 days
3. Generate a fix via local LLM (under 20 lines, one module, reversible)
4. Test via self_test() — apply if pass, discard if fail
5. Update known_errors.json with new pattern
6. One line to weekly report
"""
from __future__ import annotations

import importlib, json, re, sqlite3, time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
HEALING_LOG = BASE_DIR / "healing_log.md"
DECISIONS_LOG = BASE_DIR / "agent_decisions.md"
KNOWN_ERRORS = BASE_DIR / "known_errors.json"
PROPOSED_DIR = BASE_DIR / "proposed_fixes"
REPORT_PATH = DATA_DIR / "weekly_report.md"

def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _today(): return datetime.now().strftime("%Y-%m-%d")


# ── Step 1: Collect failure data ──

def _read_log_failures(path: Path, days: int = 7) -> list[str]:
    """Extract failure lines from a markdown log within the last N days."""
    if not path.exists(): return []
    cutoff = datetime.now() - timedelta(days=days)
    failures = []
    for line in path.read_text().splitlines():
        m = re.search(r"`(\d{4}-\d{2}-\d{2})", line)
        if m:
            try:
                d = datetime.strptime(m.group(1), "%Y-%m-%d")
                if d < cutoff: continue
            except ValueError: pass
        low = line.lower()
        if any(w in low for w in ("fail", "error", "blocked", "timeout", "denied")):
            failures.append(line.strip())
    return failures


def _read_db_failures(days: int = 7) -> list[str]:
    """Read error entries from SQLite agent_log."""
    if not DB_PATH.exists(): return []
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT action, detail FROM agent_log "
            "WHERE confidence < 0.5 AND created_at > ? "
            "ORDER BY created_at DESC LIMIT 200", (cutoff,)
        ).fetchall()
        conn.close()
        return [f"{a}: {d}" for a, d in rows]
    except Exception:
        return []


def collect_failures(days: int = 7) -> list[str]:
    healing = _read_log_failures(HEALING_LOG, days)
    decisions = _read_log_failures(DECISIONS_LOG, days)
    db = _read_db_failures(days)
    return healing + decisions + db


# ── Step 2: Identify top 3 patterns ──

_PATTERN_GROUPS = [
    ("import_error", r"(?:ModuleNotFoundError|ImportError)"),
    ("timeout", r"(?:timeout|timed out|TimeoutError)"),
    ("connection_error", r"(?:ConnectionError|ConnectionRefused|urlopen)"),
    ("permission_error", r"(?:PermissionError|Permission denied)"),
    ("sqlite_locked", r"(?:database is locked|OperationalError)"),
    ("json_error", r"(?:JSONDecodeError|json\.decoder)"),
    ("api_auth", r"(?:401|403|Unauthorized|Forbidden|API key)"),
    ("model_missing", r"(?:model.*not found|pull.*model)"),
    ("file_not_found", r"(?:FileNotFoundError|No such file)"),
    ("type_error", r"(?:TypeError|AttributeError)"),
]

def top_failure_patterns(failures: list[str], n: int = 3) -> list[tuple[str, int]]:
    counts: Counter = Counter()
    for line in failures:
        for name, pat in _PATTERN_GROUPS:
            if re.search(pat, line, re.IGNORECASE):
                counts[name] += 1; break
        else:
            counts["other"] += 1
    return counts.most_common(n)


# ── Step 3: Generate + test a fix ──

def _generate_fix_prompt(pattern: str, samples: list[str]) -> str:
    sample_text = "\n".join(samples[:5])
    return (
        f"The most frequent error in this Python project is: {pattern}\n\n"
        f"Recent occurrences:\n{sample_text}\n\n"
        "Propose a fix. Requirements:\n"
        "- Under 20 lines of Python\n"
        "- Confined to one module\n"
        "- Must be reversible (show the original and the replacement)\n"
        "- Output format:\n"
        "MODULE: <filename.py>\n"
        "EXPLANATION: <one sentence>\n"
        "ORIGINAL:\n```python\n<code to replace>\n```\n"
        "REPLACEMENT:\n```python\n<new code>\n```\n"
        "Only output this. Nothing else.\n"
    )


def _parse_fix(llm_output: str) -> dict | None:
    """Parse LLM fix proposal into structured dict."""
    m_mod = re.search(r"MODULE:\s*(\S+\.py)", llm_output)
    m_exp = re.search(r"EXPLANATION:\s*(.+)", llm_output)
    originals = re.findall(r"ORIGINAL:\s*```python\n(.*?)```", llm_output, re.DOTALL)
    replacements = re.findall(r"REPLACEMENT:\s*```python\n(.*?)```", llm_output, re.DOTALL)
    if not (m_mod and originals and replacements): return None
    original = originals[0].strip()
    replacement = replacements[0].strip()
    if replacement.count("\n") > 20: return None  # too long
    return {
        "module": m_mod.group(1),
        "explanation": m_exp.group(1).strip() if m_exp else "",
        "original": original,
        "replacement": replacement,
    }


def _save_proposal(fix: dict, pattern: str) -> Path:
    PROPOSED_DIR.mkdir(parents=True, exist_ok=True)
    mod = fix["module"].replace(".py", "")
    path = PROPOSED_DIR / f"{_today()}_{mod}.py"
    content = (
        f"# Proposed fix for: {pattern}\n"
        f"# Module: {fix['module']}\n"
        f"# Explanation: {fix['explanation']}\n"
        f"# Generated: {_now()}\n\n"
        f"# === ORIGINAL ===\n# {fix['original']}\n\n"
        f"# === REPLACEMENT ===\n{fix['replacement']}\n"
    )
    path.write_text(content); return path


def _run_self_test(module_name: str) -> bool:
    """Run a module's self_test(). Returns True if it passes."""
    name = module_name.replace(".py", "")
    try:
        mod = importlib.import_module(name)
        if hasattr(mod, "self_test"):
            return mod.self_test()
    except Exception:
        pass
    return False


def _apply_fix(fix: dict) -> bool:
    """Apply the fix by string-replacing in the target module."""
    path = BASE_DIR / fix["module"]
    if not path.exists(): return False
    src = path.read_text()
    if fix["original"] not in src: return False
    path.write_text(src.replace(fix["original"], fix["replacement"], 1))
    return True


def _revert_fix(fix: dict) -> bool:
    path = BASE_DIR / fix["module"]
    if not path.exists(): return False
    src = path.read_text()
    if fix["replacement"] not in src: return False
    path.write_text(src.replace(fix["replacement"], fix["original"], 1))
    return True


# ── Step 4: Update known_errors.json ──

def _add_known_error(pattern: str, fix_cmd: str, check_cmd: str) -> None:
    errors = json.loads(KNOWN_ERRORS.read_text()) if KNOWN_ERRORS.exists() else []
    if any(e.get("id") == f"auto-{pattern}" for e in errors): return
    errors.append({
        "id": f"auto-{pattern}", "pattern": pattern,
        "fix_command": fix_cmd, "success_check": check_cmd,
        "description": f"Auto-discovered: {pattern}",
    })
    KNOWN_ERRORS.write_text(json.dumps(errors, indent=2))


# ── Step 5: Weekly report ──

def _append_report(fixed: int, patterns: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = (f"- `{_now()}` This week I fixed {fixed} recurring issue(s) "
            f"and added {patterns} new recovery pattern(s).\n")
    with open(REPORT_PATH, "a") as f:
        if f.tell() == 0: f.write("# Weekly Self-Improvement Report\n\n")
        f.write(line)


# ── Main ──

def run() -> dict:
    """Run one improvement cycle. Returns summary dict."""
    failures = collect_failures(7)
    if not failures:
        return {"status": "clean", "failures": 0}
    top = top_failure_patterns(failures)
    if not top:
        return {"status": "no_patterns", "failures": len(failures)}
    fixed, new_patterns = 0, 0
    pattern_name = top[0][0]
    samples = [f for f in failures if re.search(
        dict(_PATTERN_GROUPS).get(pattern_name, pattern_name), f, re.IGNORECASE)]
    try:
        from agent_backend import generate
        raw = generate(_generate_fix_prompt(pattern_name, samples))
    except Exception:
        _append_report(0, 0)
        return {"status": "llm_unavailable", "top_patterns": top}
    fix = _parse_fix(raw)
    if not fix:
        _append_report(0, 0)
        return {"status": "no_valid_fix", "top_patterns": top}
    proposal_path = _save_proposal(fix, pattern_name)
    if _apply_fix(fix):
        if _run_self_test(fix["module"]):
            fixed += 1
            regex = dict(_PATTERN_GROUPS).get(pattern_name, pattern_name)
            _add_known_error(regex, f"# auto-fix applied to {fix['module']}", "true")
            new_patterns += 1
        else:
            _revert_fix(fix)
    _append_report(fixed, new_patterns)
    return {"status": "complete", "fixed": fixed, "new_patterns": new_patterns,
            "top_patterns": top, "proposal": str(proposal_path)}


def run_loop():
    """Daemon: run once every 24 hours."""
    while True:
        try: run()
        except Exception: pass
        time.sleep(86400)


def self_test() -> bool:
    """Verify failure collection and pattern detection."""
    patterns = top_failure_patterns(["timeout error", "timeout again", "import fail"])
    assert patterns[0][0] == "timeout" and patterns[0][1] == 2
    fix = _parse_fix("MODULE: test.py\nEXPLANATION: fix\nORIGINAL:\n```python\nold\n```\nREPLACEMENT:\n```python\nnew\n```")
    assert fix and fix["module"] == "test.py" and fix["original"] == "old"
    assert _parse_fix("garbage") is None, "bad input parsed"
    assert isinstance(collect_failures(1), list)
    return True

if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
