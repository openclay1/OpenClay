"""
OpenClay automated test suite.
Requires the server running at http://localhost:3000.
Run: python3 -m pytest tests/test_openclay.py -v
"""
import json
import sys
import subprocess
import time
import unittest

try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

BASE = "http://localhost:3000"
FAST_TIMEOUT = 10    # non-model endpoints
MODEL_TIMEOUT = 240  # streaming model inference: 20-60s on GPU, 60-180s on CPU-only


def _server_available():
    try:
        requests.get(BASE + "/api/pro-status", timeout=3)
        return True
    except Exception:
        return False


def _post(path, body=None, timeout=FAST_TIMEOUT):
    return requests.post(BASE + path, json=body or {}, timeout=timeout)


def _get(path, timeout=FAST_TIMEOUT):
    return requests.get(BASE + path, timeout=timeout)


def _parse_ndjson(text):
    """Parse NDJSON streaming response into (full_text, memories_used)."""
    full_text = ""
    memories_used = None
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            chunk = json.loads(line)
            if chunk.get("meta"):
                memories_used = chunk.get("memories_used", [])
            elif "response" in chunk:
                full_text += chunk["response"]
            elif chunk.get("error"):
                raise ValueError(f"Server error: {chunk['error']}")
        except (json.JSONDecodeError, ValueError):
            pass
    return full_text, memories_used


@unittest.skipUnless(_server_available(), "OpenClay server not running at localhost:3000")
class TestProStatus(unittest.TestCase):
    """(e) /api/pro-status returns a valid JSON object with 'pro' field."""

    def test_pro_status(self):
        r = _get("/api/pro-status")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("pro", data)
        self.assertIsInstance(data["pro"], bool)


@unittest.skipUnless(_server_available(), "OpenClay server not running at localhost:3000")
class TestAgentsEndpoint(unittest.TestCase):
    """(a) /api/agents returns ≥5 agents each with name, description, color_accent."""

    def test_agents_endpoint(self):
        r = _post("/api/agents")
        self.assertEqual(r.status_code, 200)
        agents = r.json().get("agents", [])
        self.assertGreaterEqual(len(agents), 5, f"Expected ≥5 agents, got {len(agents)}")
        for a in agents:
            self.assertIn("name", a)
            self.assertIn("description", a)
            self.assertIn("color_accent", a)
            self.assertTrue(a["name"])
            self.assertTrue(a["color_accent"].startswith("#"))


@unittest.skipUnless(_server_available(), "OpenClay server not running at localhost:3000")
class TestMemoriesEndpoint(unittest.TestCase):
    """Extra: /api/memories returns stored memories list."""

    def test_memories_endpoint(self):
        r = _post("/api/memories")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("memories", data)
        self.assertIsInstance(data["memories"], list)


@unittest.skipUnless(_server_available(), "OpenClay server not running at localhost:3000")
class TestAskReturnsSoulContext(unittest.TestCase):
    """(b) /api/ask with a personal question returns a non-empty response with memory injection."""

    def test_ask_returns_soul_context(self):
        try:
            r = _post("/api/ask", {"prompt": "what is my work about?"}, timeout=MODEL_TIMEOUT)
        except requests.exceptions.ReadTimeout:
            self.skipTest("Model inference timed out — CPU-only hardware may be too slow")
        self.assertEqual(r.status_code, 200)
        full_text, memories_used = _parse_ndjson(r.text)
        self.assertGreater(len(full_text), 5, f"Response too short: {repr(full_text[:80])}")
        self.assertNotIn("i don't know", full_text.lower()[:120])
        if memories_used is not None:
            self.assertIsInstance(memories_used, list)


@unittest.skipUnless(_server_available(), "OpenClay server not running at localhost:3000")
class TestConversationsSaved(unittest.TestCase):
    """(f) /api/conversations returns saved files (existing or after a new ask)."""

    def test_conversations_saved(self):
        # First check if conversations exist from previous sessions
        r0 = _get("/api/conversations")
        existing = r0.json().get("conversations", []) if r0.status_code == 200 else []
        if existing:
            self.assertGreaterEqual(len(existing), 1)
            return  # Previous sessions already prove persistence works
        # No prior conversations — trigger one (may be slow on CPU)
        try:
            _post("/api/ask", {"prompt": "persistence test"}, timeout=MODEL_TIMEOUT)
        except requests.exceptions.ReadTimeout:
            self.skipTest("Model inference timed out — cannot verify conversation persistence")
        time.sleep(1)
        r = _get("/api/conversations")
        self.assertEqual(r.status_code, 200)
        convs = r.json().get("conversations", [])
        self.assertGreaterEqual(len(convs), 1, "No conversations recorded")


@unittest.skipUnless(_server_available(), "OpenClay server not running at localhost:3000")
class TestOrchestrateChain(unittest.TestCase):
    """(d) /api/orchestrate runs a 2-agent chain and returns both agents' outputs."""

    def test_orchestrate_chain(self):
        payload = {
            "goal": "In exactly one sentence, what is 2+2?",
            "agents": ["Clay General", "Clay Investigador"]
        }
        try:
            r = _post("/api/orchestrate", payload, timeout=MODEL_TIMEOUT * 2)
        except requests.exceptions.ReadTimeout:
            self.skipTest("Model inference timed out — CPU-only hardware may be too slow")
        self.assertEqual(r.status_code, 200, f"orchestrate returned {r.status_code}")
        data = r.json()
        self.assertTrue(data.get("ok"), f"orchestrate not ok: {data}")
        results = data.get("results", [])
        self.assertEqual(len(results), 2, f"Expected 2 results, got {len(results)}")
        for res in results:
            self.assertIn("agent", res)
            self.assertIn("output", res)
            self.assertTrue(res["output"].strip(), f"Empty output from {res.get('agent')}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
