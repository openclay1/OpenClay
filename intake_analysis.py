"""
intake_analysis.py — Archetype detection, intent extraction, domain inference.
Used by intake.py. Separated to keep modules under 300 lines.
"""

import json
import subprocess

ARCHETYPE_STUCK = "stuck"
ARCHETYPE_CLEAR = "clear"
ARCHETYPE_BLANK = "blank"

STUCK_SIGNALS = [
    "frustrated", "not working", "can't figure", "don't know why",
    "keeps failing", "stuck", "broken", "tried everything",
    "nothing works", "confused", "overwhelmed", "lost",
    "help me", "struggle", "pain", "hate", "annoying",
]

CLEAR_SIGNALS = [
    "I need", "set up", "install", "configure", "build me",
    "I want a", "create a", "deploy", "automate", "pipeline",
    "workflow", "api", "database", "server", "app",
    "script", "tool", "system", "integrate",
]

BLANK_SIGNALS = [
    "I want to start", "where do I begin", "don't know where",
    "something new", "explore", "try", "get into",
    "no idea", "blank", "fresh start", "from scratch",
    "what can", "what should", "possibilities",
]

BLANK_ARCHETYPES = [
    {
        "name": "The Creator",
        "description": "You make things people consume — writing, video, music, art, code. "
                       "You need a pipeline that turns raw ideas into published work without "
                       "you managing every step.",
        "profile": "creator",
    },
    {
        "name": "The Researcher",
        "description": "You collect, read, and synthesize information — papers, articles, data, "
                       "documents. You need a system that ingests everything, finds connections, "
                       "and gives you answers from your own knowledge base.",
        "profile": "researcher",
    },
    {
        "name": "The Operator",
        "description": "You run things — a business, a team, a side hustle, a life with too many "
                       "moving parts. You need automation that handles the repetitive work so you "
                       "can focus on decisions only you can make.",
        "profile": "operator",
    },
]

POST_READY_SIGNALS = [
    "ready to post", "have content", "have a video", "have a photo",
    "have an image", "recorded a", "finished editing", "ready to publish",
    "have media", "shot a video", "took photos", "have footage",
    "just need captions", "need hashtags", "need a caption",
    "ready to go", "content is done", "post this", "upload this",
]

STRATEGY_SIGNALS = [
    "strategy", "plan", "grow", "audience", "schedule",
    "what should I", "content calendar", "ideas for",
    "how to start", "pipeline", "workflow", "long term",
]

INTAKE_MODEL = "qwen2.5:0.5b"


def ollama_generate(prompt: str, model: str = INTAKE_MODEL) -> str:
    """Generate text using Ollama. Falls back to empty string if unavailable."""
    from retry_ext import retry_call
    try:
        result = retry_call(
            subprocess.run, ["ollama", "run", model, prompt],
            capture_output=True, text=True, timeout=60,
            label="intake-ollama",
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def detect_archetype(text: str) -> str:
    """Classify user into archetype based on language signals."""
    text_lower = text.lower()

    stuck_score = sum(1 for s in STUCK_SIGNALS if s in text_lower)
    clear_score = sum(1 for s in CLEAR_SIGNALS if s in text_lower)
    blank_score = sum(1 for s in BLANK_SIGNALS if s in text_lower)

    if clear_score >= 2 or (clear_score > stuck_score and clear_score > blank_score):
        return ARCHETYPE_CLEAR
    if stuck_score >= 2 or (stuck_score > clear_score and stuck_score > blank_score):
        return ARCHETYPE_STUCK
    if blank_score >= 1:
        return ARCHETYPE_BLANK

    words = text.split()
    if len(words) > 15:
        return ARCHETYPE_CLEAR
    return ARCHETYPE_BLANK


def infer_domain(text: str) -> str:
    """Infer domain from text content."""
    text_lower = text.lower()
    domain_signals = {
        "content": ["write", "blog", "video", "youtube", "content", "publish", "post",
                     "social", "newsletter", "podcast", "article", "edit"],
        "research": ["research", "paper", "data", "analyze", "study", "document",
                      "read", "learn", "notes", "knowledge", "reference"],
        "automation": ["automate", "workflow", "email", "schedule", "task", "manage",
                        "organize", "business", "client", "invoice", "crm"],
        "development": ["code", "build", "app", "api", "deploy", "server", "database",
                         "website", "frontend", "backend", "script", "program"],
    }
    scores = {}
    for domain, signals in domain_signals.items():
        scores[domain] = sum(1 for s in signals if s in text_lower)

    if max(scores.values()) == 0:
        return "other"
    return max(scores, key=scores.get)


def extract_intent_clear(text: str) -> dict:
    """Extract structured intent from a clear user's description."""
    prompt = f"""Analyze this user request and extract their intent as JSON.
User said: "{text}"

Return ONLY valid JSON with these fields:
- "goal": one sentence describing what they want
- "tools_mentioned": list of any specific tools/technologies they mentioned
- "domain": the domain (content, research, automation, development, other)
- "urgency": low/medium/high based on their language
- "complexity": simple/moderate/complex

JSON:"""

    raw = ollama_generate(prompt)

    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except (json.JSONDecodeError, ValueError):
        pass

    domain = infer_domain(text)
    intent = {
        "goal": text.strip(),
        "tools_mentioned": [],
        "domain": domain,
        "urgency": "medium",
        "complexity": "moderate",
    }
    if domain == "content":
        intent["content_intent"] = classify_content_intent(text)
    return intent


def classify_content_intent(text: str) -> str:
    """Classify whether creator intent is 'post_ready' or 'strategy_needed'."""
    text_lower = text.lower()
    post_score = sum(1 for s in POST_READY_SIGNALS if s in text_lower)
    strategy_score = sum(1 for s in STRATEGY_SIGNALS if s in text_lower)

    if post_score > strategy_score:
        return "post_ready"
    return "strategy_needed"


def generate_lateral_question(text: str) -> str:
    """For stuck users: generate one lateral question to find the real blocker."""
    prompt = f"""A user described a problem they're having:
"{text}"

They're probably describing symptoms, not the root cause. Generate ONE short question
that approaches their problem from a completely different angle than they described.
The question should help reveal their real blocker. Just the question, nothing else."""

    response = ollama_generate(prompt)
    if response:
        return response

    text_lower = text.lower()
    if any(w in text_lower for w in ["time", "slow", "long", "hours"]):
        return "If time wasn't the issue, what would you actually build?"
    if any(w in text_lower for w in ["money", "cost", "expensive", "budget"]):
        return "What's the one thing that would make the cost irrelevant?"
    if any(w in text_lower for w in ["team", "people", "nobody", "alone"]):
        return "If you could clone yourself, which version would you send to fix this?"
    return "Walk me through what happens right before it breaks — not the error, but what you were trying to do."


def self_test() -> bool:
    """Verify archetype detection and domain inference."""
    assert detect_archetype("I need to set up a server") == "clear"
    assert detect_archetype("I'm stuck and frustrated") == "stuck"
    assert detect_archetype("I want to explore") == "blank"
    assert infer_domain("deploy my api server") == "development"
    assert infer_domain("write a blog post") == "content"
    assert classify_content_intent("ready to post my video") == "post_ready"
    return True
