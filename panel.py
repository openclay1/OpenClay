"""panel.py — Gradio web UI. Reports, does not prompt."""
import asyncio
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
_DEFAULT_DATA = {
    "what_was_built": ["Setting up..."],
    "what_its_doing": "Initializing OpenClay...",
    "what_it_needs": [],
    "drop_zone": {"label": "Tell me what to do", "action_type": "text_input"},
    "queue_status": {"pending": 0, "completed": 0, "failed": 0},
}


def _load_panel_data() -> dict:
    """Load current panel data from reporting module."""
    try:
        from reporting import get_panel_data
        return get_panel_data()
    except Exception:
        return dict(_DEFAULT_DATA)


def _format_built_section(items: list) -> str:
    if not items:
        return "*Setting up your stack...*"
    return "\n".join(f"- {item}" for item in items)


def _format_needs_section(needs: list) -> str:
    if not needs:
        return "*Nothing needed right now — you're all set.*"
    return "\n".join(
        f"- **{n.get('label', n.get('key', ''))}**"
        f"{' (required)' if n.get('required') else ' (optional)'}"
        for n in needs
    )


async def _handle_image_upload(files):
    """Triggered on file upload — delegates to caption_handler."""
    from caption_handler import handle_image_upload
    return await handle_image_upload(files, gr)


async def _handle_post_caption(caption: str, hashtags: str, files):
    """Post caption + images — delegates to caption_handler."""
    from caption_handler import handle_post_caption
    return await handle_post_caption(caption, hashtags, files)


async def _handle_drop_zone(text: str, files) -> str:
    """Handle text-only submissions from the drop zone."""
    try:
        await asyncio.sleep(0)
        if text and text.strip():
            QUEUE_DIR.mkdir(parents=True, exist_ok=True)
            task = {"source": "panel", "task_type": "profile_action",
                    "payload": {"action": "generate_outline", "topic": text.strip()}}
            with open(QUEUE_DIR / f"panel_{int(time.time())}.json", "w") as f:
                json.dump(task, f)
            return f"On it: \"{text.strip()[:60]}\" — working now."
    except Exception as e:
        return f"Error: {e}"
    return "Drop images or type something to get started."


def _handle_undo() -> str:
    """Undo the last agent action."""
    try:
        path = BASE_DIR / "agent_decisions.md"
        if path.exists():
            lines = path.read_text().splitlines(keepends=True)
            if lines:
                path.write_text("".join(lines[:-1]))
                return f"Undone: {lines[-1].strip()}"
        return "Nothing to undo."
    except Exception as e:
        return f"Undo failed: {e}"


def _stream_doing_section():
    """Stream the doing content token-by-token."""
    output_path = DATA_DIR / "first_action_output.md"
    if not output_path.exists():
        yield "*Setting up your workspace...*"
        return
    content = output_path.read_text()
    acc = ""
    for ch in content:
        acc += ch
        yield acc
        time.sleep(0.018)


def _handle_ig_connect():
    from oauth import connect_instagram
    return connect_instagram()


def _handle_ig_creds(app_id, app_secret):
    from oauth import save_app_credentials
    return save_app_credentials(app_id, app_secret)


def _get_ig_status() -> str:
    try:
        from oauth import check_instagram_ready
        s = check_instagram_ready()
        if s["connected"]:
            return "**Instagram:** Connected"
        if s["app_configured"]:
            return "**Instagram:** App configured — click Connect to authorize"
        return "**Instagram:** Not configured"
    except Exception:
        return "**Instagram:** Not configured"


def _refresh_panel():
    data = _load_panel_data()
    return (
        _format_built_section(data["what_was_built"]),
        data["what_its_doing"],
        _format_needs_section(data["what_it_needs"]),
    )


def _load_css() -> str:
    css_path = BASE_DIR / "theme.css"
    return css_path.read_text() if css_path.exists() else ""


def build_panel() -> "gr.Blocks":
    """Build the Gradio interface."""
    if gr is None:
        raise ImportError("gradio not installed — run: pip3 install gradio")
    data = _load_panel_data()
    with gr.Blocks(title="OpenClay") as panel:
        gr.Markdown("# OpenClay", elem_classes=["main-header"])
        gr.Markdown("*Your local AI infrastructure — running now.*", elem_classes=["subtitle"])
        with gr.Row():
            with gr.Column():
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("### What was built")
                    built_display = gr.Markdown(_format_built_section(data["what_was_built"]))
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("### What it needs from you")
                    needs_display = gr.Markdown(_format_needs_section(data["what_it_needs"]))
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("### Connections")
                    ig_status = gr.Markdown(_get_ig_status())
                    ig_btn = gr.Button("Connect Instagram", variant="primary", size="sm")
                    ig_result = gr.Markdown("")
                    ig_btn.click(_handle_ig_connect, outputs=[ig_result])
                    with gr.Accordion("Instagram app setup", open=False):
                        gr.Markdown("*One-time: paste your App ID and Secret from developers.facebook.com*")
                        ig_id = gr.Textbox(label="App ID", placeholder="Instagram App ID")
                        ig_sec = gr.Textbox(label="App Secret", placeholder="Instagram App Secret", type="password")
                        ig_save = gr.Button("Save credentials", variant="secondary", size="sm")
                        ig_save_res = gr.Markdown("")
                        ig_save.click(_handle_ig_creds, inputs=[ig_id, ig_sec], outputs=[ig_save_res])
            with gr.Column():
                with gr.Group(elem_classes=["section-card", "doing-card"]):
                    gr.Markdown("### What it's already doing")
                    doing_display = gr.Markdown(data["what_its_doing"])
                    s_btn = gr.Button("Stream result", variant="secondary", size="sm")
                    s_btn.click(_stream_doing_section, outputs=[doing_display])
                with gr.Group(elem_classes=["section-card"]):
                    gr.Markdown("### Your move")
                    lbl = data["drop_zone"].get("label", "Type or drop something here")
                    drop_text = gr.Textbox(label=lbl, placeholder=lbl, lines=2)
                    drop_file = gr.File(label="Drop images for Instagram", file_count="multiple")
                    drop_result = gr.Markdown("")
                    with gr.Group(visible=False, elem_classes=["section-card", "caption-card"]) as cap_grp:
                        gr.Markdown("### Caption Preview")
                        cap_analysis = gr.Markdown("")
                        cap_box = gr.Textbox(label="Caption", placeholder="Your generated caption...",
                                             lines=5, interactive=True)
                        hash_box = gr.Textbox(label="Hashtags", placeholder="#tennis #fastcourt ...",
                                              lines=2, interactive=True)
                    post_btn = gr.Button("Post to Instagram", variant="primary",
                                         visible=False, elem_classes=["post-btn"])
                    post_res = gr.Markdown("")
                    drop_file.change(_handle_image_upload, inputs=[drop_file],
                                     outputs=[cap_grp, cap_box, hash_box, cap_analysis, post_btn, drop_result])
                    post_btn.click(_handle_post_caption, inputs=[cap_box, hash_box, drop_file], outputs=[post_res])
                    go_btn = gr.Button("Go", variant="primary")
                    go_btn.click(_handle_drop_zone, inputs=[drop_text, drop_file], outputs=[drop_result])
        with gr.Row():
            undo_btn = gr.Button("Undo last action", variant="secondary", size="sm")
            undo_res = gr.Markdown("")
            undo_btn.click(_handle_undo, outputs=[undo_res])
            ref_btn = gr.Button("Refresh", variant="secondary", size="sm")
            ref_btn.click(_refresh_panel, outputs=[built_display, doing_display, needs_display])
    return panel


def launch(share: bool = False):
    """Launch the panel in the browser."""
    panel = build_panel()
    panel.launch(server_name="127.0.0.1", server_port=7861, share=share,
                 inbrowser=True, show_error=True, css=_load_css())


if __name__ == "__main__":
    launch()
