"""model_router.py — LOCAL_FAST / LOCAL_SMART / CLOUD task routing.

Three tiers:
  LOCAL_FAST  — gemma4:e4b via Ollama: formatting, scheduling, captions,
                hashtags, tweet drafting, file ops, status checks, simple Q&A.
  LOCAL_SMART — gemma4:26b via Ollama: wiki ingest/query/lint, self-build loop
                fix generation, reasoning, code review, multi-step tasks.
  CLOUD       — Only when both local tiers fail or explicit cloud-complexity:
                architecture, multi-step debugging, code gen over 50 lines.

Logic: route to appropriate local tier first. On bad response after 2 retries
→ escalate (FAST→SMART→CLOUD). Every decision logged to routing_log.md.
"""
from __future__ import annotations
import json, os, re, time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ROUTING_LOG = BASE_DIR / "routing_log.md"
ENV_PATH = BASE_DIR / ".env"

LOCAL_FAST = "LOCAL_FAST"
LOCAL_SMART = "LOCAL_SMART"
LOCAL = LOCAL_FAST  # backwards compat alias
CLOUD = "CLOUD"

# ── Model names for each tier ──
# Env overrides available: OLLAMA_MODEL_FAST, OLLAMA_MODEL_SMART
MODEL_FAST = os.environ.get("OLLAMA_MODEL_FAST", "gemma4:e4b")
MODEL_SMART = os.environ.get("OLLAMA_MODEL_SMART", "gemma4:26b")

# Keywords that signal CLOUD-tier complexity
CLOUD_SIGNALS = [
    r"architect", r"design.*(system|api|schema)", r"refactor",
    r"debug.*(multi|complex|chain)", r"generate.*\b(\d{2,})\s*lines",
    r"compare.*(approach|framework|pattern)", r"explain.*(why|how).*(?:fail|bug|crash)",
    r"review.*(code|pr|pull)", r"plan.*(migration|deploy|upgrade)",
    r"write.*(module|class|service)\b",
]
_CLOUD_RE = [re.compile(p, re.IGNORECASE) for p in CLOUD_SIGNALS]

# Task types routed to LOCAL_FAST (lightweight, quick responses)
LOCAL_FAST_TYPES = {
    "formatting", "scheduling", "caption", "hashtag", "tweet", "draft",
    "file_op", "status_check", "retry", "simple_qa", "select_profile",
    "install_stack", "start_agent",
}
# Task types routed to LOCAL_SMART (reasoning, analysis, generation)
LOCAL_SMART_TYPES = {
    "wiki_ingest", "wiki_query", "wiki_lint", "self_build_fix",
    "code_review", "summarize", "explain", "generate",
}
# Combined for backwards compat
LOCAL_TASK_TYPES = LOCAL_FAST_TYPES | LOCAL_SMART_TYPES


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log_route(task_desc: str, tier: str, success: bool,
               escalated: bool = False, tokens: int = 0, reason: str = ""):
    """Append one line to routing_log.md."""
    status = "OK" if success else "FAIL"
    esc = " (escalated)" if escalated else ""
    tok = f" tokens={tokens}" if tokens else ""
    line = (f"- `{_now()}` **{tier}{esc}** `{status}` — "
            f"`{task_desc[:80]}`{tok} {reason}\n")
    try:
        with open(ROUTING_LOG, "a") as f:
            if f.tell() == 0:
                f.write("# Routing Log\n\nAll model routing decisions.\n\n")
            f.write(line)
    except FileNotFoundError:
        with open(ROUTING_LOG, "w") as f:
            f.write("# Routing Log\n\nAll model routing decisions.\n\n")
            f.write(line)


def _read_env_key(key: str) -> str:
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            l = line.strip()
            if l and not l.startswith("#") and "=" in l:
                k, _, v = l.partition("=")
                if k.strip() == key: return v.strip()
    return os.environ.get(key, "")


def _has_cloud_key() -> bool:
    """Check if an API key is configured for cloud providers."""
    return bool(_read_env_key("ANTHROPIC_API_KEY") or _read_env_key("OPENAI_API_KEY"))


def classify(prompt: str, task_type: str = "") -> str:
    """Classify a task as LOCAL_FAST, LOCAL_SMART, or CLOUD."""
    tt = task_type.lower()
    if tt in LOCAL_FAST_TYPES: return LOCAL_FAST
    if tt in LOCAL_SMART_TYPES: return LOCAL_SMART
    for pat in _CLOUD_RE:
        if pat.search(prompt): return CLOUD
    m = re.search(r"generate.*?(\d+)\s*lines", prompt, re.IGNORECASE)
    if m and int(m.group(1)) > 50: return CLOUD
    # Default: LOCAL_FAST for short prompts, LOCAL_SMART for longer ones
    return LOCAL_SMART if len(prompt) > 500 else LOCAL_FAST


def _is_bad_response(text: str) -> bool:
    """Return True if the response looks empty or malformed."""
    if not text or not text.strip():
        return True
    if len(text.strip()) < 3:
        return True
    # Check for obvious error patterns
    lower = text.strip().lower()
    if lower.startswith("error:") or lower.startswith("failed:"):
        return True
    return False


def _call_local(prompt: str, model: str | None = None) -> str:
    """Call the local Ollama backend via agent_backend."""
    from agent_backend import generate, get_model
    m = model or get_model()
    return generate(prompt, model=m)


def _call_cloud(prompt: str) -> str:
    """Call cloud API (Anthropic preferred, OpenAI fallback)."""
    anthropic_key = _read_env_key("ANTHROPIC_API_KEY")
    if anthropic_key:
        return _call_anthropic(prompt, anthropic_key)
    openai_key = _read_env_key("OPENAI_API_KEY")
    if openai_key:
        return _call_openai(prompt, openai_key)
    raise RuntimeError("No cloud API key configured (ANTHROPIC_API_KEY or OPENAI_API_KEY)")


def _call_anthropic(prompt: str, api_key: str) -> str:
    """Call Anthropic Messages API."""
    import urllib.request
    from permissions import check_domain
    url = "https://api.anthropic.com/v1/messages"
    if not check_domain(url): raise RuntimeError("api.anthropic.com not in allowlist")
    body = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        blocks = data.get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    except Exception as e:
        raise RuntimeError(f"Anthropic API error: {e}")


def _call_openai(prompt: str, api_key: str) -> str:
    """Call OpenAI Chat Completions API."""
    import urllib.request
    from permissions import check_domain
    url = "https://api.openai.com/v1/chat/completions"
    if not check_domain(url): raise RuntimeError("api.openai.com not in allowlist")
    body = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"OpenAI API error: {e}")


def _try_local(prompt: str, model: str, tier: str, task_desc: str) -> str | None:
    """Attempt 2 calls to a local model. Returns result or None."""
    for attempt in range(2):
        try:
            result = _call_local(prompt, model)
            if not _is_bad_response(result):
                _log_route(task_desc, tier, True)
                return result
        except Exception: pass
        if attempt < 1: time.sleep(1)
    return None

def route(prompt: str, task_type: str = "", model: str | None = None) -> str:
    """Route: LOCAL_FAST → LOCAL_SMART → CLOUD. Escalates on failure."""
    tier = classify(prompt, task_type)
    task_desc = task_type or prompt[:60].replace("\n", " ")
    # If CLOUD but no key, downgrade to LOCAL_SMART
    if tier == CLOUD and not _has_cloud_key():
        tier = LOCAL_SMART
        _log_route(task_desc, "CLOUD→SMART", True, reason="no cloud key")
    # ── LOCAL_FAST ──
    if tier == LOCAL_FAST:
        m = model or MODEL_FAST
        result = _try_local(prompt, m, LOCAL_FAST, task_desc)
        if result: return result
        _log_route(task_desc, LOCAL_FAST, False, reason="escalating to LOCAL_SMART")
        tier = LOCAL_SMART  # fall through
    # ── LOCAL_SMART ──
    if tier == LOCAL_SMART:
        m = model or MODEL_SMART
        result = _try_local(prompt, m, LOCAL_SMART, task_desc)
        if result: return result
        if _has_cloud_key():
            _log_route(task_desc, LOCAL_SMART, False, reason="escalating to CLOUD")
            try:
                result = _call_cloud(prompt)
                if not _is_bad_response(result):
                    _log_route(task_desc, CLOUD, True, escalated=True); return result
            except Exception as e:
                _log_route(task_desc, CLOUD, False, escalated=True, reason=str(e)[:60]); raise
        _log_route(task_desc, LOCAL_SMART, False, reason="no cloud key, returning best local")
        return _call_local(prompt, model or MODEL_SMART)
    # ── CLOUD ──
    try:
        result = _call_cloud(prompt)
        if not _is_bad_response(result):
            _log_route(task_desc, CLOUD, True); return result
        raise RuntimeError("Cloud returned bad response")
    except Exception as cloud_err:
        _log_route(task_desc, CLOUD, False, reason=str(cloud_err)[:60])
        result = _try_local(prompt, model or MODEL_SMART, LOCAL_SMART, task_desc)
        if result: return result
        result = _try_local(prompt, model or MODEL_FAST, LOCAL_FAST, task_desc)
        if result: return result
        raise


def self_test() -> bool:
    """Verify three-tier classification, bad-response detection, and logging."""
    # LOCAL_FAST tasks
    assert classify("draft a tweet about AI", "tweet") == LOCAL_FAST
    assert classify("format this markdown", "formatting") == LOCAL_FAST
    assert classify("what time is it", "simple_qa") == LOCAL_FAST
    # LOCAL_SMART tasks
    assert classify("wiki ingest new page", "wiki_ingest") == LOCAL_SMART
    assert classify("explain this concept", "explain") == LOCAL_SMART
    assert classify("generate fix", "self_build_fix") == LOCAL_SMART
    # CLOUD tasks
    assert classify("architect a microservices system") == CLOUD
    assert classify("design the API schema for auth") == CLOUD
    assert classify("generate 100 lines of Python") == CLOUD
    assert classify("refactor the entire codebase") == CLOUD
    # Short prompt defaults to FAST, long to SMART
    assert classify("hello") == LOCAL_FAST
    assert classify("x " * 300) == LOCAL_SMART
    # Model constants
    assert MODEL_FAST == "gemma4:e4b"
    assert MODEL_SMART == "gemma4:26b"
    # Bad response detection
    assert _is_bad_response("") is True
    assert _is_bad_response("  ") is True
    assert _is_bad_response("ok") is True
    assert _is_bad_response("error: timeout") is True
    assert _is_bad_response("Here is your answer.") is False
    assert isinstance(_has_cloud_key(), bool)
    _log_route("self_test", LOCAL_FAST, True, reason="self_test run")
    assert ROUTING_LOG.exists(), "routing_log not created"
    return True


if __name__ == "__main__":
    print("self_test:", self_test())
