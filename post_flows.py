"""post_flows.py — Tweet and Instagram post flows for the tools panel."""
# Working app: 2040419672282087424anomalia939
import json
import time
from pathlib import Path

try:
    import gradio as gr
except ImportError:
    gr = None

BASE_DIR = Path(__file__).parent
QUEUE_DIR = BASE_DIR / "queue"

def _show(val=True):
    return gr.update(visible=val)

def _hide():
    return gr.update(visible=False)

def _verb(text: str) -> str:
    return f'<span class="status-verb">{text}</span>'


def hide_post_all(status=""):
    return (status, "", "", _hide(), _hide(),
            _hide(), "", _hide())


_STRIP_PREFIXES = ("tweet:", "here's", "here is", "sure!", "sure,",
                   "of course", "absolutely", "here you go")
_STRIP_STARTS = ("would you", "do you", "should i", "let me know",
                 "want me", "shall i", "feel free", "i can also")

def clean_tweet(raw: str) -> str:
    t = raw.strip()
    if (t.startswith('"') and t.endswith('"')) or \
       (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    low = t.lower()
    for pfx in _STRIP_PREFIXES:
        if low.startswith(pfx):
            t = t[len(pfx):].strip().lstrip(":").lstrip(",").strip()
            low = t.lower()
    return "\n".join(ln for ln in t.splitlines()
                     if not any(ln.strip().lower().startswith(q)
                                for q in _STRIP_STARTS)).strip()[:280]


def handle_create_post(topic, files):
    has_files = bool(files)
    has_topic = bool(topic and topic.strip())
    if not has_files and not has_topic:
        yield hide_post_all()
        return
    if has_files:
        yield from instagram_flow(topic, files)
        return
    yield from twitter_flow(topic.strip())


def instagram_flow(topic, files):
    import shutil
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}
    inbox = BASE_DIR / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    image_paths, names = [], []
    yield hide_post_all(_verb("Reading your images..."))
    if not isinstance(files, list):
        files = [files]
    for f in files:
        src = Path(str(f))
        dest = inbox / src.name
        try:
            shutil.copy2(str(src), str(dest))
            names.append(src.name)
            if src.suffix.lower() in IMAGE_EXTS:
                image_paths.append(str(dest))
        except Exception as e:
            yield hide_post_all(f"**Error:** Could not copy {src.name} — {e}")
            return
    if not image_paths:
        yield hide_post_all("**Error:** No image files found.")
        return
    yield hide_post_all(_verb("Finding the story..."))
    try:
        from vision_caption import generate_caption_from_images
        result = generate_caption_from_images(image_paths)
    except Exception as e:
        yield hide_post_all(f"**Error:** Vision model failed — {e}")
        return
    if result.get("error"):
        yield hide_post_all(f"**Error:** {result['error']}")
        return
    yield hide_post_all(_verb("Writing..."))
    time.sleep(0.4)
    caption = result.get("caption", "")
    hashtags = result.get("hashtags", "")
    full_caption = f"{caption}\n\n{hashtags}" if hashtags else caption
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    n_img = len(image_paths)
    task = {
        "source": "panel", "task_type": "instagram_post",
        "payload": {
            "action": "carousel_post" if n_img > 1 else "single_post",
            "caption": full_caption, "images": image_paths,
        },
    }
    with open(QUEUE_DIR / f"ig_post_{int(time.time()*1000)}.json", "w") as fh:
        json.dump(task, fh)
    h = _hide()
    yield (_verb("Done."), caption, hashtags,
           _show(), _show(), h, "", h)


def twitter_flow(topic: str):
    yield hide_post_all(_verb("Reading your intention..."))
    time.sleep(0.6)
    yield hide_post_all(_verb("Thinking..."))
    try:
        from agent_backend import generate
        from wiki_engine import build_tweet_prompt
        raw = generate(build_tweet_prompt(topic))
    except Exception as e:
        yield hide_post_all(f"**Error:** {e}")
        return
    yield hide_post_all(_verb("Drafting..."))
    time.sleep(0.8)
    yield hide_post_all(_verb("Sharpening..."))
    time.sleep(0.6)
    tweet = clean_tweet(raw)
    if not tweet:
        yield hide_post_all("**Error:** Could not generate tweet.")
        return
    h = _hide()
    yield (_verb("Draft ready."), "", "", h, h,
           _show(), tweet, _show())


def handle_confirm_tweet(tweet_text):
    def _out(msg):
        return (msg, _hide(), _show(), _show(), _show())
    if not tweet_text or not tweet_text.strip():
        return _out("**Error:** No tweet text.")
    from twitter_post import validate_twitter_credentials, post_tweet
    v = validate_twitter_credentials()
    if v["status"] != "ready":
        return _out(f"**Error:** {v['detail']}")
    result = post_tweet(tweet_text.strip())
    if result.get("success"):
        tid = result.get("tweet_id", "")
        try:
            from wiki_engine import log_posted_tweet
            log_posted_tweet(tweet_text.strip(), tweet_id=tid)
        except Exception:
            pass
        try:
            from memory import record_success
            record_success("tweet_post", "tweepy", f"id:{tid}")
        except Exception:
            pass
        return _out(f"**Posted.** Tweet ID: {tid}")
    err = result.get("error", "Unknown error")
    try:
        from memory import record_failure
        record_failure("tweet_post", err)
    except Exception:
        pass
    return _out(f"**Error:** {err}")


def copy_text(caption, hashtags):
    return f"{caption}\n\n{hashtags}" if hashtags.strip() else caption


def self_test() -> bool:
    """Verify tweet cleaning."""
    assert clean_tweet('"Hello world"') == "Hello world"
    assert clean_tweet("Here's your tweet: test") == "your tweet: test"
    assert clean_tweet("Would you like me to post?") == ""
    assert len(clean_tweet("x" * 300)) <= 280, "over 280"
    assert clean_tweet("Tweet: Real content here") == "Real content here"
    return True
