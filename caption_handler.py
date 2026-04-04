"""
caption_handler.py — Handles image upload → caption generation → post queueing.
Keeps panel.py under 300 lines by owning the caption workflow.
"""
from __future__ import annotations

import asyncio
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


async def handle_image_upload(files, gr_module):
    """Triggered on file upload. If images, generate caption automatically."""
    gr = gr_module
    await asyncio.sleep(0)

    if not files:
        return (
            gr.update(visible=False),
            "", "", "",
            gr.update(visible=False),
            "",
        )

    image_paths, names = _ingest_files(files)

    if not image_paths:
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        for name in names:
            dest = BASE_DIR / "inbox" / name
            task = {
                "source": "panel",
                "task_type": "profile_action",
                "payload": {"action": "ingest_document", "path": str(dest)},
            }
            ts = int(time.time() * 1000)
            with open(QUEUE_DIR / f"panel_{ts}_{name}.json", "w") as fh:
                json.dump(task, fh)
        return (
            gr.update(visible=False),
            "", "", "",
            gr.update(visible=False),
            f"{len(names)} files received — processing now.",
        )

    from vision_caption import generate_caption_from_images
    result = generate_caption_from_images(image_paths)

    if result.get("error"):
        return (
            gr.update(visible=True),
            "", "", "",
            gr.update(visible=True),
            f"Caption generation failed: {result['error']}. "
            "You can write one manually below.",
        )

    analysis = result.get("analysis", "")
    caption = result.get("caption", "")
    hashtags = result.get("hashtags", "")
    note = result.get("note", "")

    analysis_text = f"*{analysis}*" if analysis else ""
    if note:
        analysis_text = (
            f"{analysis_text}\n\n⚠️ {note}" if analysis_text
            else f"⚠️ {note}"
        )

    img_count = len(image_paths)
    status = (
        f"{img_count} image{'s' if img_count > 1 else ''} analyzed — "
        "caption ready. Edit below, then hit Post."
    )

    return (
        gr.update(visible=True),
        caption,
        hashtags,
        analysis_text,
        gr.update(visible=True),
        status,
    )


async def handle_post_caption(caption: str, hashtags: str, files):
    """Queue caption + images for Instagram posting."""
    await asyncio.sleep(0)
    if not caption.strip():
        return "Write a caption first."

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
            "action": (
                "carousel_post" if len(image_paths) > 1 else "single_post"
            ),
            "caption": full_caption,
            "images": image_paths,
        },
    }
    ts = int(time.time() * 1000)
    with open(QUEUE_DIR / f"ig_post_{ts}.json", "w") as fh:
        json.dump(task, fh)

    count = len(image_paths)
    return (
        f"Queued for posting — {count} image{'s' if count != 1 else ''} "
        "with your caption."
    )
