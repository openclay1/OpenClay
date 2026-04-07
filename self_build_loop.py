"""self_build_loop.py — Constrained autonomous development loop.

Reads recurring issues from logs, generates a small fix via LLM, backs up the
target file, applies the change, runs ALL self_tests, keeps or rolls back.

Hard constraints:
  - Allowlisted files only (no safety/runtime modules).
  - Max 20 lines changed, one file per cycle.
  - Backup saved to backups/ before every edit.
  - All 21 self_tests must pass or the change is reverted automatically.
"""
from __future__ import annotations
import importlib, json, re, shutil, time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
BACKUP_DIR = BASE_DIR / "backups"
BUILD_LOG = BASE_DIR / "self_build_log.md"

# ── Allowlist: only these files may be edited ──
ALLOWED_FILES = {"post_flows.py", "mobile_bridge.py", "model_router.py",
                 "wiki_engine.py", "panel.py"}

# ── Log sources to scan for recurring issues ──
LOG_SOURCES = [
    BASE_DIR / "healing_log.md",
    BASE_DIR / "bridge_log.md",
    BASE_DIR / "routing_log.md",
    BASE_DIR / "agent_decisions.md",
]

# ── All modules with self_test ──
_TEST_MODULES = [
    "intake_analysis", "installer", "agent_backend", "agent", "panel",
    "memory", "twitter_post", "post_flows", "vision_caption", "wiki_engine",
    "credential_store", "oauth", "input_guard", "retry_ext", "watchdog",
    "permissions", "self_improver", "browser_agent", "model_router",
    "mobile_bridge", "self_build_loop",
]

def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def _ts(): return datetime.now().strftime("%Y%m%d_%H%M%S")


def _log_build(action: str, detail: str, success: bool):
    status = "OK" if success else "FAIL"
    line = f"- `{_now()}` **{action}** `{status}` — {detail}\n"
    try:
        with open(BUILD_LOG, "a") as f:
            if f.tell() == 0: f.write("# Self-Build Log\n\nAutonomous changes to OpenClay.\n\n")
            f.write(line)
    except FileNotFoundError:
        with open(BUILD_LOG, "w") as f:
            f.write("# Self-Build Log\n\nAutonomous changes to OpenClay.\n\n")
            f.write(line)


# ── Step 1: Collect issues from logs ──

_ISSUE_PATTERNS = [
    ("timeout", r"(?:timeout|timed out|TimeoutError)"),
    ("connection", r"(?:ConnectionError|ConnectionRefused|urlopen)"),
    ("import_error", r"(?:ModuleNotFoundError|ImportError)"),
    ("json_error", r"(?:JSONDecodeError|json\.decoder)"),
    ("type_error", r"(?:TypeError|AttributeError)"),
    ("file_missing", r"(?:FileNotFoundError|No such file)"),
    ("blocked", r"(?:BLOCKED|blocked|denied)"),
    ("empty_response", r"(?:empty.?response|no.?response|bad.?response)"),
]

def collect_issues(days: int = 7) -> list[str]:
    """Read failure lines from all log sources within the last N days."""
    cutoff = datetime.now() - timedelta(days=days)
    issues = []
    for src in LOG_SOURCES:
        if not src.exists(): continue
        for line in src.read_text().splitlines():
            m = re.search(r"`(\d{4}-\d{2}-\d{2})", line)
            if m:
                try:
                    if datetime.strptime(m.group(1), "%Y-%m-%d") < cutoff: continue
                except ValueError: pass
            low = line.lower()
            if any(w in low for w in ("fail", "error", "timeout", "blocked", "denied")):
                issues.append(line.strip())
    return issues


def top_issues(issues: list[str], n: int = 3) -> list[tuple[str, int]]:
    counts: Counter = Counter()
    for line in issues:
        for name, pat in _ISSUE_PATTERNS:
            if re.search(pat, line, re.IGNORECASE): counts[name] += 1; break
        else: counts["other"] += 1
    return counts.most_common(n)


# ── Step 2: Generate fix via LLM ──

def _build_fix_prompt(pattern: str, samples: list[str]) -> str:
    sample_text = "\n".join(samples[:5])
    allowed = ", ".join(sorted(ALLOWED_FILES))
    return (
        f"The most frequent recurring issue in this Python project is: {pattern}\n\n"
        f"Recent occurrences:\n{sample_text}\n\n"
        f"You may ONLY edit one of these files: {allowed}\n"
        "Propose a fix. Requirements:\n"
        "- Under 20 lines of Python changed\n"
        "- One file only\n"
        "- Must be reversible (show original and replacement)\n"
        "- Output format:\n"
        "FILE: <filename.py>\n"
        "EXPLANATION: <one sentence>\n"
        "ORIGINAL:\n```python\n<exact code to replace>\n```\n"
        "REPLACEMENT:\n```python\n<new code>\n```\n"
    )


def _parse_fix(llm_output: str) -> dict | None:
    m_file = re.search(r"FILE:\s*(\S+\.py)", llm_output)
    m_exp = re.search(r"EXPLANATION:\s*(.+)", llm_output)
    originals = re.findall(r"ORIGINAL:\s*```python\n(.*?)```", llm_output, re.DOTALL)
    replacements = re.findall(r"REPLACEMENT:\s*```python\n(.*?)```", llm_output, re.DOTALL)
    if not (m_file and originals and replacements): return None
    filename = m_file.group(1)
    if filename not in ALLOWED_FILES: return None
    original = originals[0].strip()
    replacement = replacements[0].strip()
    if replacement.count("\n") > 20: return None
    return {"file": filename, "explanation": m_exp.group(1).strip() if m_exp else "",
            "original": original, "replacement": replacement}


# ── Step 3: Backup + apply + test + rollback ──

def _backup(filename: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    src = BASE_DIR / filename
    dest = BACKUP_DIR / f"{_ts()}_{filename}"
    shutil.copy2(str(src), str(dest))
    return dest

def _restore(backup_path: Path, filename: str):
    shutil.copy2(str(backup_path), str(BASE_DIR / filename))

def _apply(fix: dict) -> bool:
    path = BASE_DIR / fix["file"]
    if not path.exists(): return False
    src = path.read_text()
    if fix["original"] not in src: return False
    path.write_text(src.replace(fix["original"], fix["replacement"], 1))
    return True

def run_all_tests() -> tuple[bool, list[str]]:
    """Run every module's self_test(). Returns (all_pass, list_of_failures)."""
    failures = []
    for name in _TEST_MODULES:
        try:
            mod = importlib.reload(importlib.import_module(name))
            if hasattr(mod, "self_test"):
                if not mod.self_test(): failures.append(name)
        except Exception as e:
            failures.append(f"{name}: {e}")
    return len(failures) == 0, failures


# ── Main cycle ──

def run_once() -> dict:
    """Run one improvement cycle. Returns summary dict."""
    issues = collect_issues(7)
    if not issues:
        _log_build("scan", "no recurring issues found", True)
        return {"status": "clean", "issues": 0}
    top = top_issues(issues)
    if not top:
        return {"status": "no_patterns", "issues": len(issues)}
    pattern_name, count = top[0]
    samples = [i for i in issues if re.search(
        dict(_ISSUE_PATTERNS).get(pattern_name, pattern_name), i, re.IGNORECASE)]
    # Generate fix via LOCAL_SMART (gemma4:26b)
    try:
        from model_router import route, MODEL_SMART
        raw = route(_build_fix_prompt(pattern_name, samples),
                    task_type="self_build_fix", model=MODEL_SMART)
    except Exception as e:
        _log_build("llm_generate", f"LLM unavailable: {e}", False)
        return {"status": "llm_unavailable", "top": top}
    fix = _parse_fix(raw)
    if not fix:
        _log_build("parse_fix", f"no valid fix parsed for {pattern_name}", False)
        return {"status": "no_valid_fix", "top": top}
    # Backup
    backup = _backup(fix["file"])
    _log_build("backup", f"{fix['file']} → {backup.name}", True)
    # Apply
    if not _apply(fix):
        _log_build("apply", f"original code not found in {fix['file']}", False)
        return {"status": "apply_failed", "file": fix["file"]}
    # Test ALL modules
    all_pass, failures = run_all_tests()
    if all_pass:
        _log_build("applied", f"{fix['file']}: {fix['explanation']}", True)
        return {"status": "applied", "file": fix["file"], "explanation": fix["explanation"]}
    # Rollback
    _restore(backup, fix["file"])
    _log_build("rollback", f"{fix['file']} — tests failed: {failures[:3]}", False)
    return {"status": "rolled_back", "file": fix["file"], "failures": failures[:3]}


def run_loop(interval: int = 86400):
    """Daemon: run once per interval (default 24h)."""
    while True:
        try: run_once()
        except Exception as e: _log_build("loop_error", str(e)[:120], False)
        time.sleep(interval)


def self_test() -> bool:
    """Verify allowlist, issue collection, parsing, and backup/restore."""
    # Allowlist enforcement
    assert "agent.py" not in ALLOWED_FILES
    assert "permissions.py" not in ALLOWED_FILES
    assert "input_guard.py" not in ALLOWED_FILES
    assert "post_flows.py" in ALLOWED_FILES
    # Issue collection
    issues = collect_issues(7)
    assert isinstance(issues, list)
    # Pattern detection
    top = top_issues(["timeout error x", "timeout again", "import fail"])
    assert top[0][0] == "timeout" and top[0][1] == 2
    # Fix parsing — valid
    fix = _parse_fix(
        "FILE: post_flows.py\nEXPLANATION: add timeout\n"
        "ORIGINAL:\n```python\nold_code\n```\n"
        "REPLACEMENT:\n```python\nnew_code\n```")
    assert fix and fix["file"] == "post_flows.py"
    # Fix parsing — blocked file
    bad = _parse_fix(
        "FILE: agent.py\nEXPLANATION: hack\n"
        "ORIGINAL:\n```python\nx\n```\n"
        "REPLACEMENT:\n```python\ny\n```")
    assert bad is None, "blocked file accepted"
    # Fix parsing — garbage
    assert _parse_fix("garbage") is None
    # Backup + restore roundtrip
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    test_file = BASE_DIR / "post_flows.py"
    original = test_file.read_text()
    bk = _backup("post_flows.py")
    assert bk.exists(), "backup not created"
    _restore(bk, "post_flows.py")
    assert test_file.read_text() == original, "restore changed content"
    bk.unlink()  # cleanup test backup
    # Log
    _log_build("self_test", "all checks passed", True)
    return True


if __name__ == "__main__":
    print("self_test:", self_test())
