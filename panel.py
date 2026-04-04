"""panel.py — Minimal OpenClay dashboard. Images → Instagram. Text → Twitter."""
import json
import time
from pathlib import Path

try:
    import gradio as gr
except ImportError:
    gr = None

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
QUEUE_DIR = BASE_DIR / "queue"


def _hide_all(status="", show_inputs=True):
    vis_in = gr.update(visible=show_inputs)
    return (status, "", "",
            gr.update(visible=False), gr.update(visible=False),
            gr.update(visible=False), "", gr.update(visible=False),
            vis_in, vis_in, vis_in)


def _handle_create_post(topic, files):
    has_files = bool(files)
    has_topic = bool(topic and topic.strip())

    if not has_files and not has_topic:
        yield _hide_all()
        return

    # ── IMAGES PATH: Instagram caption ──
    if has_files:
        yield from _instagram_flow(topic, files)
        return

    # ── TEXT-ONLY PATH: Tweet draft ──
    yield from _twitter_flow(topic.strip())


def _verb(text: str) -> str:
    """Wrap a status verb in the animated span markup."""
    return f'<span class="status-verb">{text}</span>'


def _instagram_flow(topic, files):
    import shutil
    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}
    inbox = BASE_DIR / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    image_paths, names = [], []

    yield _hide_all(_verb("Reading your images..."))

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
            yield _hide_all(f"**Error:** Could not copy {src.name} — {e}")
            return

    n_img = len(image_paths)
    if not image_paths:
        yield _hide_all("**Error:** No image files found. Drop .jpg, .png, or .webp.")
        return

    yield _hide_all(_verb("Finding the story..."))

    try:
        from vision_caption import generate_caption_from_images
        result = generate_caption_from_images(image_paths)
    except Exception as e:
        yield _hide_all(f"**Error:** Vision model failed — {e}")
        return

    if result.get("error"):
        yield _hide_all(f"**Error:** {result['error']}")
        return

    yield _hide_all(_verb("Writing..."))
    time.sleep(0.4)

    caption = result.get("caption", "")
    hashtags = result.get("hashtags", "")
    model = result.get("model", "vision")

    full_caption = f"{caption}\n\n{hashtags}" if hashtags else caption
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    task = {
        "source": "panel", "task_type": "instagram_post",
        "payload": {
            "action": "carousel_post" if n_img > 1 else "single_post",
            "caption": full_caption, "images": image_paths,
        },
    }
    with open(QUEUE_DIR / f"ig_post_{int(time.time()*1000)}.json", "w") as fh:
        json.dump(task, fh)

    _v = gr.update(visible=False)
    yield (
        _verb("Done."),
        caption, hashtags,
        gr.update(visible=True), gr.update(visible=True),
        _v, "", _v,
        _v, _v, _v,
    )


_STRIP_PREFIXES = ("tweet:", "here's", "here is", "sure!", "sure,",
                   "of course", "absolutely", "here you go")
_STRIP_STARTS = ("would you", "do you", "should i", "let me know",
                 "want me", "shall i", "feel free", "i can also")

def _clean_tweet(raw: str) -> str:
    t = raw.strip()
    if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
        t = t[1:-1].strip()
    low = t.lower()
    for pfx in _STRIP_PREFIXES:
        if low.startswith(pfx):
            t = t[len(pfx):].strip().lstrip(":").lstrip(",").strip()
            low = t.lower()
    return "\n".join(ln for ln in t.splitlines()
                     if not any(ln.strip().lower().startswith(q) for q in _STRIP_STARTS)
                     ).strip()[:280]


def _twitter_flow(topic: str):
    yield _hide_all(_verb("Reading your intention..."))
    time.sleep(0.6)
    yield _hide_all(_verb("Thinking..."))
    try:
        from agent_backend import generate
        from wiki_engine import build_tweet_prompt
        prompt = build_tweet_prompt(topic)
        raw = generate(prompt)
    except Exception as e:
        yield _hide_all(f"**Error:** {e}")
        return
    # Post-LLM verb sequence — each gets real screen time
    yield _hide_all(_verb("Drafting..."))
    time.sleep(0.8)
    yield _hide_all(_verb("Sharpening..."))
    time.sleep(0.6)
    tweet = _clean_tweet(raw)
    if not tweet:
        yield _hide_all("**Error:** Could not generate tweet. Try again.")
        return
    # Show draft, hide all input elements
    _v = gr.update(visible=False)
    yield (
        _verb("Draft ready."),
        "", "",
        _v, _v,
        gr.update(visible=True), tweet, gr.update(visible=True),
        _v, _v, _v,
    )


def _handle_confirm_tweet(tweet_text):
    _show = gr.update(visible=True)
    _hide = gr.update(visible=False)
    def _out(msg):
        return (msg, _hide, _hide, _show, _show, _show)
    if not tweet_text or not tweet_text.strip():
        return _out("**Error:** No tweet text.")
    from twitter_post import check_twitter_ready, post_tweet
    if not check_twitter_ready():
        return _out(
            "**Error:** Twitter credentials not set. "
            "Add TWITTER_API_KEY/SECRET + ACCESS_TOKEN/SECRET to .env"
        )
    result = post_tweet(tweet_text.strip())
    if result.get("success"):
        tid = result.get("tweet_id", "")
        try:
            from wiki_engine import log_posted_tweet
            log_posted_tweet(tweet_text.strip(), tweet_id=tid)
        except Exception:
            pass  # wiki logging is best-effort
        return _out(f"**Posted.** Tweet ID: {tid}")
    return _out(f"**Error:** {result.get('error', 'Unknown error')}")


def _copy_text(caption, hashtags):
    return f"{caption}\n\n{hashtags}" if hashtags.strip() else caption


def _load_css() -> str:
    p = BASE_DIR / "theme.css"
    return p.read_text() if p.exists() else ""


def build_panel() -> "gr.Blocks":
    if gr is None:
        raise ImportError("gradio not installed — run: pip3 install gradio")

    with gr.Blocks(title="OpenClay") as panel:
        gr.Markdown("# *OpenClay*", elem_classes=["app-title"])
        gr.Markdown(
            "Drop images or describe what to post.",
            elem_classes=["app-sub"],
        )

        # Drop zone
        drop_file = gr.File(
            label="Drop your images here",
            file_count="multiple", elem_classes=["drop-zone"],
        )

        # Topic
        topic_box = gr.Textbox(
            label="What do you want to tweet about?",
            placeholder="e.g. announce OpenClay exists, match day energy, Sunday doubles...",
            lines=1, elem_classes=["topic-input"],
        )

        # Go
        go_btn = gr.Button("Create & Post", variant="primary",
                           elem_classes=["go-btn"])

        # Status
        status_md = gr.Markdown("", elem_classes=["status-bar"])

        # ── Instagram result card ──
        with gr.Group(visible=False, elem_classes=["result-card"]) as result_grp:
            gr.Markdown("### Instagram Caption", elem_classes=["result-heading"])
            caption_box = gr.Textbox(label="Caption", lines=6,
                                     interactive=True, elem_classes=["result-text"])
            hashtag_box = gr.Textbox(label="Hashtags", lines=2,
                                     interactive=True, elem_classes=["result-text"])
        copy_btn = gr.Button("Copy to Clipboard", variant="secondary",
                             visible=False, elem_classes=["copy-btn"])

        # ── Twitter draft card ──
        with gr.Group(visible=False, elem_classes=["result-card"]) as tweet_grp:
            gr.Markdown("### Tweet Draft", elem_classes=["result-heading"])
            tweet_box = gr.Textbox(label="Tweet", lines=3,
                                   interactive=True, elem_classes=["result-text"],
                                   max_lines=4)
        confirm_btn = gr.Button("Confirm & Post to Twitter", variant="primary",
                                visible=False, elem_classes=["go-btn"])
        tweet_status = gr.Markdown("", elem_classes=["status-bar"])

        # Wire: main flow
        go_btn.click(
            _handle_create_post,
            inputs=[topic_box, drop_file],
            outputs=[status_md, caption_box, hashtag_box,
                     result_grp, copy_btn,
                     tweet_grp, tweet_box, confirm_btn,
                     drop_file, topic_box, go_btn],
        )

        # Wire: copy
        copy_output = gr.Textbox(visible=False)
        copy_btn.click(_copy_text, inputs=[caption_box, hashtag_box],
                       outputs=[copy_output])

        # Wire: confirm tweet — posts, then restores input UI
        confirm_btn.click(_handle_confirm_tweet, inputs=[tweet_box],
                          outputs=[tweet_status, tweet_grp, confirm_btn,
                                   drop_file, topic_box, go_btn])

    return panel


def launch(share: bool = False):
    panel = build_panel()
    panel.launch(server_name="127.0.0.1", server_port=7861, share=share,
                 inbrowser=True, show_error=True, css=_load_css())


if __name__ == "__main__":
    launch()
