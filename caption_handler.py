"""
caption_handler.py — Handles image upload → caption generation → post queueing.
Streaming generators yield progress updates visible in the panel.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
QUEUE_DIR = BASE_DIR / "queue"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif"}


def _ingest_files(files) -> tuple[list[str], list[str]]:
    """Copy uploaded files to inbox, return (image_paths, all_names)."""
    if not isinstance(files, list):
        files = [files]
    inbox = BASE_DIR / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    image_paths, names = [], []
    for f in files:
        src = Path(str(f))
        dest = inbox / src.name
        shutil.copy2(str(src), str(dest))
        names.append(src.name)
        if src.suffix.lower() in IMAGE_EXTS:
            image_paths.append(str(dest))
    return image_paths, names


def _no_change(gr, status):
    """6-tuple that only updates the status field."""
    return (gr.update(), gr.update(), gr.update(),
            gr.update(), gr.update(), status)


def _hidden(gr, status):
    """6-tuple with caption group and post button hidden."""
    return (gr.update(visible=False), "", "", "",
            gr.update(visible=False), status)


def handle_image_upload_streaming(files, gr):
    """Generator: yields progress updates, then final caption result."""
    # Stage 0: immediate feedback
    if not files:
        yield _hidden(gr, "")
        return

    yield _no_change(gr, "**Working...** Receiving files...")

    # Stage 1: ingest
    try:
        image_paths, names = _ingest_files(files)
    except Exception as e:
        yield _hidden(gr, f"**Error:** Failed to receive files — {e}")
        return

    n = len(names)
    yield _no_change(gr, f"**Working...** {n} file{'s' if n != 1 else ''} received.")

    # Non-image files — queue and exit
    if not image_paths:
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        for name in names:
            dest = BASE_DIR / "inbox" / name
            task = {"source": "panel", "task_type": "profile_action",
                    "payload": {"action": "ingest_document", "path": str(dest)}}
            ts = int(time.time() * 1000)
            with open(QUEUE_DIR / f"panel_{ts}_{name}.json", "w") as fh:
                json.dump(task, fh)
        yield _hidden(gr, f"**Done.** {n} files queued for processing.")
        return

    # Stage 2: vision analysis
    img_count = len(image_paths)
    yield _no_change(
        gr,
        f"**Analyzing...** Sending {img_count} image{'s' if img_count != 1 else ''} "
        "to vision model. This may take 30-60 seconds..."
    )

    try:
        from vision_caption import generate_caption_from_images
        result = generate_caption_from_images(image_paths)
    except Exception as e:
        yield (
            gr.update(visible=True), "", "", "",
            gr.update(visible=True),
            f"**Error:** Vision model failed — {e}. Write a caption manually below.",
        )
        return

    # Stage 3: check for errors
    if result.get("error"):
        yield (
            gr.update(visible=True), "", "", "",
            gr.update(visible=True),
            f"**Error:** {result['error']}. You can write a caption manually below.",
        )
        return

    yield _no_change(gr, "**Generating caption...** Almost done...")

    # Stage 4: success — show caption
    analysis = result.get("analysis", "")
    caption = result.get("caption", "")
    hashtags = result.get("hashtags", "")
    note = result.get("note", "")
    model = result.get("model", "vision model")

    analysis_text = f"*{analysis}*" if analysis else ""
    if note:
        analysis_text = f"{analysis_text}\n\n⚠️ {note}" if analysis_text else f"⚠️ {note}"

    status = (
        f"**Done.** {img_count} image{'s' if img_count != 1 else ''} "
        f"analyzed via {model}. Edit the caption below, then hit Post."
    )

    yield (
        gr.update(visible=True),
        caption,
        hashtags,
        analysis_text,
        gr.update(visible=True),
        status,
    )


def handle_post_caption_sync(caption: str, hashtags: str, files) -> str:
    """Queue caption + images for Instagram posting. Returns status."""
    if not caption.strip():
        return "**Error:** Write a caption first."

    full_caption = (
        f"{caption.strip()}\n\n{hashtags.strip()}"
        if hashtags.strip() else caption.strip()
    )

    image_paths = []
    if files:
        if not isinstance(files, list):
            files = [files]
        for f in files:
            src = Path(str(f))
            dest = BASE_DIR / "inbox" / src.name
            if dest.exists() and dest.suffix.lower() in IMAGE_EXTS:
                image_paths.append(str(dest))

    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    task = {
        "source": "panel",
        "task_type": "instagram_post",
        "payload": {
            "action": "carousel_post" if len(image_paths) > 1 else "single_post",
            "caption": full_caption,
            "images": image_paths,
        },
    }
    ts = int(time.time() * 1000)
    with open(QUEUE_DIR / f"ig_post_{ts}.json", "w") as fh:
        json.dump(task, fh)

    count = len(image_paths)
    return (
        f"**Queued for posting.** {count} image{'s' if count != 1 else ''} "
        "with your caption."
    )
