#!/usr/bin/env python3
"""
openclay.py — OpenClay CLI utility
COANA Labs · Local AI Research Assistant

Usage:
    python openclay.py --metrics      Print task metrics summary table
    python openclay.py --help         Show this help text
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
SANDBOX_DIR = BASE_DIR / "sandbox"
TASK_METRICS_FILE = SANDBOX_DIR / "logs" / "task_metrics.jsonl"


def print_help():
    print("""
  OpenClay CLI — COANA Labs
  ─────────────────────────

  Usage:
    python openclay.py --metrics      Print task metrics summary table
    python openclay.py --help         Show this help text

  Commands:
    --metrics     Read sandbox/logs/task_metrics.jsonl and print a formatted
                  table showing avg steps, avg retries, success rate, and
                  last run time for each task type.

    --help        Show this help message.

  About:
    OpenClay v1.3.0 · All processing local · COANA Labs, Puerto Rico
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

    # Group by task_name
    by_name = {}
    for e in entries:
        name = e.get("task_name", "unknown")
        by_name.setdefault(name, []).append(e)

    col = 35
    print(f"\n{'Task Name':<{col}} {'Avg Steps':>10} {'Avg Retries':>12} {'Success Rate':>13} {'Last Run':<20}")
    print("\u2500" * (col + 10 + 13 + 14 + 21))
    for name in sorted(by_name):
        runs = by_name[name]
        avg_steps   = sum(r.get("total_steps", 0) for r in runs) / len(runs)
        avg_retries = sum(r.get("retry_count", 0) for r in runs) / len(runs)
        success_rate = sum(1 for r in runs if r.get("success")) / len(runs) * 100
        last_run = max(r.get("end_time", "") for r in runs)[:16]
        print(f"{name:<{col}} {avg_steps:>10.1f} {avg_retries:>12.1f} {success_rate:>12.0f}% {last_run:<20}")

    print(f"\nTotal task runs: {len(entries)}\n")


def main():
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print_help()
        return

    if "--metrics" in args:
        print_task_metrics()
        return

    print(f"Unknown argument: {args[0]}")
    print("Run 'python openclay.py --help' for usage.")
    sys.exit(1)


if __name__ == "__main__":
    main()
