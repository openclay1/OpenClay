#!/usr/bin/env python3
"""
openclay.py — OpenClay CLI utility
COANA Labs · Local AI Research Assistant

Usage:
    python openclay.py --metrics      Print task metrics summary table
    python openclay.py --hunt-grants  Run grant intelligence brief for each entry in grants_targets.json
    python openclay.py --help         Show this help text
"""
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).parent
SANDBOX_DIR = BASE_DIR / "sandbox"
TASK_METRICS_FILE = SANDBOX_DIR / "logs" / "task_metrics.jsonl"
GRANTS_FILE = BASE_DIR / "grants_targets.json"
SERVER_URL = "http://localhost:3000"


def print_help():
    print("""
  OpenClay CLI — COANA Labs
  ─────────────────────────

  Usage:
    python openclay.py --metrics        Print task metrics summary table
    python openclay.py --hunt-grants    Run grant intelligence briefs for all entries
                                        in grants_targets.json, save to sandbox/output/grants/
    python openclay.py --help           Show this help text

  Commands:
    --metrics      Read sandbox/logs/task_metrics.jsonl and print a formatted
                   table: Task Name | Avg Steps | Avg Retries | Success Rate | Last Run

    --hunt-grants  For each grant in grants_targets.json, runs the grant_intelligence_brief
                   demo task via the OpenClay server, then prints a ranked table of
                   alignment scores. Server must be running (python clay_server.py).

    --help         Show this help message.

  About:
    OpenClay v1.3.1 · All processing local · COANA Labs, Puerto Rico
    URL: coana.lab
""")


def print_task_metrics():
    """Print a summary table of task_metrics.jsonl to stdout."""
    if not TASK_METRICS_FILE.exists():
        print("No metrics file found at", TASK_METRICS_FILE)
        print("Run some tasks first.")
        return

    entries = []
    for line in TASK_METRICS_FILE.read_text("utf-8").splitlines():
        if line.strip():
            try:
                entries.append(json.loads(line))
            except Exception:
                pass

    if not entries:
        print("No metrics recorded yet.")
        return

    by_name = {}
    for e in entries:
        name = e.get("task_name", "unknown")
        by_name.setdefault(name, []).append(e)

    col = 35
    print(f"\n{'Task Name':<{col}} {'Avg Steps':>10} {'Avg Retries':>12} {'Success Rate':>13} {'Last Run':<20}")
    print("\u2500" * (col + 10 + 13 + 14 + 21))
    for name in sorted(by_name):
        runs = by_name[name]
        avg_steps    = sum(r.get("total_steps", 0) for r in runs) / len(runs)
        avg_retries  = sum(r.get("retry_count", 0) for r in runs) / len(runs)
        success_rate = sum(1 for r in runs if r.get("success")) / len(runs) * 100
        last_run     = max(r.get("end_time", "") for r in runs)[:16]
        print(f"{name:<{col}} {avg_steps:>10.1f} {avg_retries:>12.1f} {success_rate:>12.0f}% {last_run:<20}")

    print(f"\nTotal task runs: {len(entries)}\n")


def _server_call(path, body=None, method=None):
    """Make an HTTP call to the OpenClay server. Returns parsed JSON or None."""
    url = SERVER_URL + path
    data = json.dumps(body).encode() if body is not None else None
    m = method or ("POST" if data else "GET")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"} if data else {},
                                 method=m)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:
        return None


def _poll_task(task_id, timeout=180, interval=4):
    """Poll task until complete or failed. Returns task dict or None."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = _server_call(f"/api/tasks/{task_id}", method="GET")
        if task and task.get("status") in ("complete", "failed"):
            return task
        time.sleep(interval)
    return None


def hunt_grants():
    """Run grant intelligence brief for each entry in grants_targets.json."""
    # Validate prereqs
    if not GRANTS_FILE.exists():
        print(f"grants_targets.json not found at {GRANTS_FILE}")
        print("Create it or run: python openclay.py --help")
        sys.exit(1)

    grants = json.loads(GRANTS_FILE.read_text("utf-8"))
    if not grants:
        print("grants_targets.json is empty.")
        return

    # Check server
    ping = _server_call("/api/tasks", method="GET")
    if ping is None:
        print("OpenClay server not reachable at", SERVER_URL)
        print("Start it with: python clay_server.py")
        sys.exit(1)

    output_dir = SANDBOX_DIR / "output" / "grants"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n  OpenClay Grant Hunter — processing {len(grants)} grant(s)\n")
    results = []

    for i, grant in enumerate(grants, 1):
        name     = grant.get("name", f"Grant {i}")
        focus    = grant.get("focus", "")
        deadline = grant.get("deadline", "?")
        url      = grant.get("url", "")

        print(f"  [{i}/{len(grants)}] {name}")
        print(f"         Focus: {focus[:70]}")

        # Build a goal that combines grant focus with context
        goal = f"{focus}. (Grant: {name}, Deadline: {deadline})"

        # Create task
        resp = _server_call("/api/tasks/create", {"goal": goal, "demo_type": "grant_intelligence_brief"})
        if not resp or not resp.get("ok"):
            print(f"         Failed to create task: {resp}")
            results.append({"name": name, "score": None, "brief": "—", "deadline": deadline})
            continue

        task_id = resp["task_id"]
        print(f"         Task: {task_id[:8]}... polling", end="", flush=True)

        task = _poll_task(task_id, timeout=180, interval=5)
        print()  # newline after dots

        if not task or task.get("status") != "complete":
            print(f"         Timed out or failed")
            results.append({"name": name, "score": None, "brief": "—", "deadline": deadline})
            continue

        # Get output file
        output_file = task.get("output_file", "")
        score = None
        brief_dest = "—"

        if output_file:
            src = SANDBOX_DIR / output_file
            if src.exists():
                content = src.read_text("utf-8")
                m = re.search(r"SCORE:\s*(\d+)", content)
                if m:
                    score = int(m.group(1))

                safe_name = re.sub(r"[^\w-]", "_", name.lower())[:35]
                dst = output_dir / f"{safe_name}_brief.md"
                dst.write_text(content, "utf-8")
                brief_dest = str(dst.relative_to(BASE_DIR))

        score_str = f"{score}/10" if score is not None else "—"
        print(f"         Score: {score_str}  →  {brief_dest}")
        results.append({"name": name, "score": score, "brief": brief_dest,
                         "deadline": deadline, "url": url})

    # Sort by score descending (None goes last)
    results.sort(key=lambda r: r["score"] if isinstance(r["score"], int) else -1, reverse=True)

    # Print ranked table
    col = 30
    print(f"\n  {'Grant Name':<{col}} {'Score':>7}  {'Deadline':<12}  Brief")
    print("  " + "\u2500" * 80)
    for r in results:
        score_str = f"{r['score']}/10" if isinstance(r["score"], int) else "  —"
        marker = "  \u2b50" if isinstance(r["score"], int) and r["score"] >= 8 else "    "
        print(f"{marker} {r['name']:<{col}} {score_str:>7}  {r['deadline']:<12}  {r['brief']}")

    top = [r for r in results if isinstance(r["score"], int) and r["score"] >= 8]
    if top:
        print(f"\n  {len(top)} high-alignment grant(s) (score \u2265 8): {', '.join(r['name'] for r in top)}")
    print(f"\n  Briefs saved to: sandbox/output/grants/\n")


def main():
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print_help()
        return

    if "--metrics" in args:
        print_task_metrics()
        return

    if "--hunt-grants" in args:
        hunt_grants()
        return

    print(f"Unknown argument: {args[0]}")
    print("Run 'python openclay.py --help' for usage.")
    sys.exit(1)


if __name__ == "__main__":
    main()
