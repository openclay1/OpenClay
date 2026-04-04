"""
researcher.py — Document ingestion, local RAG, citation management.
"""

import json
import subprocess
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
KB_DIR = BASE_DIR / "knowledge_base"


def _log_decision(action: str, detail: str, confidence: float = 1.0):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) VALUES (?, ?, ?, ?)",
            ("researcher", action, detail, confidence),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    with open(BASE_DIR / "agent_decisions.md", "a") as f:
        f.write(f"- **researcher**: {action} — {detail} (confidence: {confidence})\n")


def _generate(prompt: str) -> str:
    """Generate text via the configured agent backend."""
    from agent_backend import generate
    return generate(prompt)


def ensure_dirs():
    for d in ["inbox", "processed", "notes", "citations"]:
        (KB_DIR / d).mkdir(parents=True, exist_ok=True)


def handle_action(payload: dict) -> str:
    action = payload.get("action", "")
    ensure_dirs()

    if action == "ingest_document":
        return ingest_document(payload.get("path", ""))
    elif action == "search":
        return search_notes(payload.get("query", ""))
    elif action == "summarize":
        return summarize_document(payload.get("path", ""))
    return f"Unknown researcher action: {action}"


def ingest_document(path: str) -> str:
    """Ingest a document: extract text, generate summary, store."""
    ensure_dirs()
    source = Path(path)
    if not source.exists():
        return f"File not found: {path}"

    # Extract text
    text = ""
    if source.suffix == ".pdf":
        try:
            r = subprocess.run(["pdftotext", str(source), "-"],
                              capture_output=True, text=True, timeout=30)
            text = r.stdout
        except Exception:
            text = f"[PDF extraction failed for {source.name}]"
    elif source.suffix in (".txt", ".md", ".csv"):
        text = source.read_text(errors="replace")
    else:
        text = f"[Unsupported format: {source.suffix}]"

    # Generate summary
    if text and not text.startswith("["):
        summary = _generate(
            f"Summarize this document in 3-5 bullet points:\n\n{text[:3000]}"
        )
    else:
        summary = text

    # Save note
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    note_path = KB_DIR / "notes" / f"{timestamp}-{source.stem}.md"
    with open(note_path, "w") as f:
        f.write(f"# {source.name}\n\n")
        f.write(f"**Source:** {source.name}\n")
        f.write(f"**Ingested:** {datetime.now().isoformat()}\n\n")
        f.write(f"## Summary\n{summary}\n\n")
        f.write(f"## Full Text\n{text[:5000]}\n")

    # Move to processed
    dest = KB_DIR / "processed" / source.name
    import shutil
    shutil.move(str(source), str(dest))

    _log_decision("document ingested", f"{source.name} -> {note_path.name}")
    return str(note_path)


def search_notes(query: str) -> str:
    """Simple keyword search across notes."""
    ensure_dirs()
    results = []
    notes_dir = KB_DIR / "notes"
    for note in notes_dir.glob("*.md"):
        content = note.read_text(errors="replace")
        if query.lower() in content.lower():
            # Extract first relevant line
            for line in content.splitlines():
                if query.lower() in line.lower():
                    results.append(f"- **{note.name}**: {line.strip()[:100]}")
                    break

    if not results:
        return f"No results for '{query}'"
    return "\n".join(results[:20])


def summarize_document(path: str) -> str:
    """Generate a detailed summary of a document."""
    source = Path(path)
    if not source.exists():
        return f"File not found: {path}"

    text = source.read_text(errors="replace")
    summary = _generate(
        f"Provide a detailed summary of this document. Include key findings, "
        f"main arguments, and important data points:\n\n{text[:4000]}"
    )
    return summary or "Summary generation failed — model may not be ready yet."
