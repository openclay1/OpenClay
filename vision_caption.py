"""
vision_caption.py — Analyze images with a vision model and generate
Instagram carousel captions in the Fast Court Tennis style.
Primary: Ollama llava/llava-llama3 (local, free). Fallback: Claude/GPT-4o.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "openclay.db"
ENV_PATH = BASE_DIR / ".env"

FAST_COURT_STYLE = (
    "You write Instagram captions for Fast Court Tennis — a high-energy, "
    "community-driven tennis brand. Style rules:\n"
    "- Opening hook: short, punchy, exciting (use emojis sparingly but well)\n"
    "- Body: 2-3 sentences, energetic and conversational, celebrating the "
    "tennis community, the grind, improvement, and love of the game\n"
    "- Call to action: invite engagement (tag a partner, drop your score, "
    "share your court)\n"
    "- Hashtags: 15-20 relevant tennis/fitness hashtags at the end\n"
    "- Tone: motivational but real, never corporate, like a coach who's also "
    "your friend\n"
    "- If it's a carousel, mention swiping through\n"
)

CAPTION_PROMPT = (
    "You are a social media manager for Fast Court Tennis.\n\n"
    f"{FAST_COURT_STYLE}\n"
    "Look at the image(s). Write ONE finished Instagram caption.\n\n"
    "RULES — FOLLOW EXACTLY:\n"
    "- Output the FINAL caption only. Ready to copy-paste and post.\n"
    "- NO planning. NO step lists. NO reasoning. NO 'Here's what I'll do'.\n"
    "- NO questions. NO 'Would you like'. NO 'Let me know'. NO 'Should I'.\n"
    "- NO tool lists. NO 'You'll need'. NO suggestions for next steps.\n"
    "- Just the caption text, then hashtags. Nothing else.\n\n"
    "FORMAT (exactly this, nothing more):\n"
    "[CAPTION]\n(the complete ready-to-post caption)\n\n"
    "[HASHTAGS]\n(15-20 hashtags on one line)"
)


def _log_decision(action: str, detail: str, confidence: float = 1.0):
    """Log to agent_log table and decisions file."""
    try:
        c = sqlite3.connect(str(DB_PATH))
        c.execute("INSERT INTO agent_log (module,action,detail,confidence) VALUES (?,?,?,?)",
                  ("vision_caption", action, detail, confidence))
        c.commit(); c.close()
    except Exception: pass
    try:
        with open(BASE_DIR / "agent_decisions.md", "a") as f:
            f.write(f"- **vision_caption**: {action} — {detail} ({confidence})\n")
    except Exception: pass


def _read_env_key(key: str) -> str:
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            l = line.strip()
            if l and not l.startswith("#") and "=" in l:
                k, _, v = l.partition("=")
                if k.strip() == key: return v.strip()
    return os.environ.get(key, "")


def _encode_image(path: Path) -> tuple[str, str]:
    """Read an image file and return (base64_data, media_type)."""
    mime, _ = mimetypes.guess_type(str(path))
    if not mime or not mime.startswith("image/"):
        mime = "image/jpeg"
    data = path.read_bytes()
    return base64.standard_b64encode(data).decode("ascii"), mime


def _is_image(path: Path) -> bool:
    """Check if a file is an image based on extension."""
    return path.suffix.lower() in {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif",
    }


def generate_caption_from_images(image_paths: list[str]) -> dict:
    """Analyze images and generate a Fast Court Tennis caption.

    Returns dict with keys: analysis, caption, hashtags, error.
    """
    paths = [Path(p) for p in image_paths if _is_image(Path(p))]
    if not paths:
        return {"error": "No valid image files found."}

    names = ", ".join(p.name for p in paths)
    _log_decision("caption_generation_started", f"{len(paths)} images: {names}")

    # 1. Primary: Ollama llava (local vision, free)
    result = _generate_via_ollama_vision(paths)
    if not result.get("error"):
        _log_decision("caption_generated", f"via Ollama {result.get('model', 'llava')}", 0.9)
        return result

    # 2. Fallback: Claude claude-opus-4-5 via Anthropic SDK
    api_key = _read_env_key("ANTHROPIC_API_KEY")
    if api_key:
        result = _generate_via_claude(paths, api_key)
        if not result.get("error"):
            _log_decision("caption_generated", "via Claude claude-opus-4-5", 0.95)
            return result

    # 3. Fallback: OpenAI GPT-4o
    openai_key = _read_env_key("OPENAI_API_KEY")
    if openai_key:
        result = _generate_via_openai(paths, openai_key)
        if not result.get("error"):
            _log_decision("caption_generated", "via GPT-4o", 0.9)
            return result

    # 4. Last resort: Ollama text-only (no vision)
    result = _generate_via_ollama_text(paths)
    if not result.get("error"):
        _log_decision("caption_generated", "via Ollama text-only", 0.6)
        return result

    return {"error": "No vision model available. Install llava via: ollama pull llava"}


def _generate_via_claude(paths: list[Path], api_key: str) -> dict:
    """Fallback: Claude claude-opus-4-5 vision."""
    try:
        import anthropic
    except ImportError:
        return {"error": "anthropic SDK not installed"}
    content = []
    for p in paths[:10]:
        b64, mime = _encode_image(p)
        content.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}})
    content.append({"type": "text", "text": CAPTION_PROMPT})
    try:
        resp = anthropic.Anthropic(api_key=api_key).messages.create(
            model="claude-opus-4-5-20250918", max_tokens=1024,
            messages=[{"role": "user", "content": content}])
        return _parse_caption_response(resp.content[0].text)
    except Exception as e:
        return {"error": f"Claude API error: {e}"}


def _generate_via_openai(paths: list[Path], api_key: str) -> dict:
    """Fallback: GPT-4o vision."""
    try:
        import openai
    except ImportError:
        return {"error": "openai SDK not installed"}
    content = [{"type": "text", "text": CAPTION_PROMPT}]
    for p in paths[:10]:
        b64, mime = _encode_image(p)
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    try:
        resp = openai.OpenAI(api_key=api_key).chat.completions.create(
            model="gpt-4o", max_tokens=1024,
            messages=[{"role": "user", "content": content}])
        return _parse_caption_response(resp.choices[0].message.content)
    except Exception as e:
        return {"error": f"OpenAI API error: {e}"}


OLLAMA_URL = "http://localhost:11434"
LLAVA_MODELS = ["llava-llama3", "llava", "llava:13b", "llava:7b"]


def _detect_llava_model() -> str | None:
    """Check which llava model is available locally."""
    try:
        import requests
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        if resp.status_code != 200:
            return None
        models = resp.json().get("models", [])
        local = {m["name"].split(":")[0] for m in models} | {m["name"] for m in models}
        return next((c for c in LLAVA_MODELS if c in local), None)
    except Exception:
        return None


def _generate_via_ollama_vision(paths: list[Path]) -> dict:
    """Primary: generate caption with Ollama llava vision model."""
    try:
        import requests
    except ImportError:
        return {"error": "requests not installed"}

    model = _detect_llava_model()
    if not model:
        return {"error": "No llava model found. Run: ollama pull llava"}

    # Ollama /api/generate accepts images as base64 array
    images_b64 = []
    for p in paths[:4]:  # llava handles ~4 images well
        b64, _ = _encode_image(p)
        images_b64.append(b64)

    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model,
                "prompt": CAPTION_PROMPT,
                "images": images_b64,
                "stream": False,
            },
            timeout=120,
        )
        if resp.status_code == 200:
            text = resp.json().get("response", "")
            result = _parse_caption_response(text)
            result["model"] = model
            return result
        return {"error": f"Ollama {model} returned {resp.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"error": "Ollama not running. Start with: ollama serve"}
    except Exception as e:
        return {"error": f"Ollama vision error: {e}"}


def _generate_via_ollama_text(paths: list[Path]) -> dict:
    """Last resort: Ollama text-only caption (no vision)."""
    try:
        import requests
    except ImportError:
        return {"error": "requests not installed"}

    filenames = ", ".join(p.name for p in paths)
    prompt = (
        f"{FAST_COURT_STYLE}\n\n"
        f"I'm posting {len(paths)} tennis images ({filenames}).\n"
        "Write the FINAL caption only. No planning. No questions.\n\n"
        "Format:\n[CAPTION]\n(caption)\n\n[HASHTAGS]\n(15-20 hashtags)"
    )
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": "qwen2.5:3b-instruct-q4_K_M", "prompt": prompt,
                  "stream": False},
            timeout=60,
        )
        if resp.status_code == 200:
            text = resp.json().get("response", "")
            result = _parse_caption_response(text)
            result["note"] = "Generated without vision (text-only). Review carefully."
            return result
        return {"error": f"Ollama returned {resp.status_code}"}
    except Exception as e:
        return {"error": f"Ollama error: {e}"}


def _parse_caption_response(text: str) -> dict:
    """Parse the structured caption response into components."""
    result = {"raw": text, "analysis": "", "caption": "", "hashtags": ""}

    # Extract [ANALYSIS] section
    if "[ANALYSIS]" in text:
        after = text.split("[ANALYSIS]", 1)[1]
        end = after.find("[CAPTION]") if "[CAPTION]" in after else len(after)
        result["analysis"] = after[:end].strip()

    # Extract [CAPTION] section
    if "[CAPTION]" in text:
        after = text.split("[CAPTION]", 1)[1]
        end = after.find("[HASHTAGS]") if "[HASHTAGS]" in after else len(after)
        result["caption"] = after[:end].strip()

    # Extract [HASHTAGS] section
    if "[HASHTAGS]" in text:
        result["hashtags"] = text.split("[HASHTAGS]", 1)[1].strip()

    # If no sections found, treat entire text as caption
    if not result["caption"]:
        result["caption"] = text.strip()

    # Strip questions, planning, and reasoning the model might add
    _STRIP = (
        "would you like", "do you want", "should i", "let me know",
        "shall i", "do you need", "want me to", "i can also", "feel free",
        "here's what", "here is what", "step 1", "step 2", "step 3",
        "first,", "next,", "then,", "finally,", "to do this",
        "you'll need", "you will need", "tools needed", "requirements:",
        "plan:", "approach:", "strategy:", "let's", "i'll",
    )
    for f in ("caption", "analysis"):
        result[f] = "\n".join(
            ln for ln in result[f].splitlines()
            if not any(ln.strip().lower().startswith(q) for q in _STRIP)
        ).strip()
    return result
