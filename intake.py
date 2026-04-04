"""
intake.py — Conversational onboarding, max 3 exchanges.
Powered by Qwen 2.5 0.5B on first run (no API key needed).
Outputs intent JSON to data/intent.json and queues it.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from intake_analysis import (
    ARCHETYPE_STUCK, ARCHETYPE_CLEAR, ARCHETYPE_BLANK,
    BLANK_ARCHETYPES,
    detect_archetype, extract_intent_clear, generate_lateral_question,
)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
QUEUE_DIR = BASE_DIR / "queue"


def _log_decision(action: str, detail: str, confidence: float = 1.0):
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute(
            "INSERT INTO agent_log (module, action, detail, confidence) VALUES (?, ?, ?, ?)",
            ("intake", action, detail, confidence),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    decisions_path = BASE_DIR / "agent_decisions.md"
    line = f"- **intake**: {action} — {detail} (confidence: {confidence})\n"
    with open(decisions_path, "a") as f:
        f.write(line)


class IntakeSession:
    """Manages a conversational intake session, max 3 exchanges."""

    def __init__(self):
        self.exchanges: list[dict] = []
        self.archetype: str | None = None
        self.intent: dict | None = None
        self.complete = False

    def process(self, user_input: str) -> dict:
        """
        Process one user message. Returns:
        {"response": str, "complete": bool, "intent": dict | None}
        """
        exchange_num = len(self.exchanges) + 1
        self.exchanges.append({"role": "user", "text": user_input})

        if exchange_num == 1:
            return self._handle_first_exchange(user_input)

        if self.archetype == ARCHETYPE_STUCK:
            return self._handle_stuck_followup(user_input)

        if self.archetype == ARCHETYPE_BLANK:
            return self._handle_blank_followup(user_input)

        if exchange_num >= 3:
            return self._force_complete()

        return {
            "response": "Tell me more about what you're trying to accomplish.",
            "complete": False,
            "intent": None,
        }

    def _handle_first_exchange(self, user_input: str) -> dict:
        self.archetype = detect_archetype(user_input)
        _log_decision(
            f"classified as {self.archetype}",
            f"exchange 1: '{user_input[:80]}...'",
            0.8,
        )

        if self.archetype == ARCHETYPE_CLEAR:
            self.intent = extract_intent_clear(user_input)
            self.intent["archetype"] = ARCHETYPE_CLEAR
            self.intent["raw_input"] = user_input
            self.complete = True
            self._save_intent()
            return {"response": "Got it. Building your stack now.", "complete": True, "intent": self.intent}

        if self.archetype == ARCHETYPE_STUCK:
            question = generate_lateral_question(user_input)
            return {"response": question, "complete": False, "intent": None}

        # Blank slate
        lines = ["Here are three paths I can build for you right now:\n"]
        for i, arch in enumerate(BLANK_ARCHETYPES, 1):
            lines.append(f"**{i}. {arch['name']}** — {arch['description']}\n")
        lines.append("Which one sounds most like you? Or tell me something else entirely.")
        return {"response": "\n".join(lines), "complete": False, "intent": None}

    def _handle_stuck_followup(self, user_input: str) -> dict:
        self.intent = extract_intent_clear(
            self.exchanges[0]["text"] + " " + user_input
        )
        self.intent["archetype"] = ARCHETYPE_STUCK
        self.intent["real_blocker"] = user_input
        self.intent["raw_input"] = self.exchanges[0]["text"]
        self.complete = True
        self._save_intent()
        return {"response": "I see the real issue. Building your stack now.", "complete": True, "intent": self.intent}

    def _handle_blank_followup(self, user_input: str) -> dict:
        selected = self._parse_blank_selection(user_input)
        if selected:
            self.intent = {
                "archetype": ARCHETYPE_BLANK,
                "selected_identity": selected["name"],
                "profile": selected["profile"],
                "goal": f"Set up a full {selected['profile']} pipeline",
                "domain": selected["profile"],
                "tools_mentioned": [],
                "urgency": "medium",
                "complexity": "moderate",
                "raw_input": user_input,
            }
        else:
            self.intent = extract_intent_clear(user_input)
            self.intent["archetype"] = ARCHETYPE_BLANK
            self.intent["raw_input"] = user_input

        self.complete = True
        self._save_intent()
        label = selected["name"] if selected else "your"
        return {"response": f"Building {label} stack now.", "complete": True, "intent": self.intent}

    def _force_complete(self) -> dict:
        all_text = " ".join(e["text"] for e in self.exchanges if e["role"] == "user")
        self.intent = extract_intent_clear(all_text)
        self.intent["archetype"] = self.archetype or "unknown"
        self.intent["raw_input"] = all_text
        self.complete = True
        self._save_intent()
        return {"response": "Building your stack now.", "complete": True, "intent": self.intent}

    def _parse_blank_selection(self, text: str) -> dict | None:
        text_lower = text.lower().strip()
        for i, arch in enumerate(BLANK_ARCHETYPES):
            if (
                str(i + 1) in text_lower
                or arch["name"].lower() in text_lower
                or arch["profile"] in text_lower
            ):
                return arch
        return None

    def _save_intent(self):
        """Save intent to data/intent.json and queue it."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)

        with open(DATA_DIR / "intent.json", "w") as f:
            json.dump(self.intent, f, indent=2)

        queue_item = {
            "source": "intake",
            "task_type": "select_profile",
            "payload": self.intent,
        }
        with open(QUEUE_DIR / "intake_complete.json", "w") as f:
            json.dump(queue_item, f, indent=2)

        try:
            conn = sqlite3.connect(str(DB_PATH))
            conn.execute(
                "INSERT INTO queue_items (source, task_type, payload, status) VALUES (?, ?, ?, ?)",
                ("intake", "select_profile", json.dumps(self.intent), "pending"),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

        _log_decision(
            "intake complete",
            f"archetype={self.intent.get('archetype')}, domain={self.intent.get('domain')}, "
            f"goal={self.intent.get('goal', '')[:60]}",
        )
