"""panel.py — OpenClay dashboard."""
import re, time
from pathlib import Path
try:
    import gradio as gr
except ImportError:
    gr = None

BASE_DIR = Path(__file__).parent

def _show(val=True): return gr.update(visible=val)
def _hide(): return gr.update(visible=False)
def _verb(t): return f'<span class="status-verb">{t}</span>'


# ─── Intent detection ───

_P = {  # pattern groups
    "tweet": [r"\b(?:post|send|write)\s+(?:a\s+)?(?:\w+\s+)*tweet\b",
              r"\btweet\s+(that|about|saying|on|something)\b", r"^tweet\s+",
              r"\b(?:post|tweet)\s+(?:to|on)\s+(?:twitter|x)\b",
              r"^post\s+(?:about|something|this)\b",
              r"^post\s+(?:a\s+)?(?:\w+\s+)*(?:about|on)\b"],
    "direct": [r"\b(?:post|tweet)\s+this\s+directly\b",
               r"\b(?:post|tweet)\s+(?:now|immediately)\b"],
    "wiki_init": [r"\b(?:build|create|init(?:ialize)?|setup)\s+(?:my\s+)?wiki\b"],
    "wiki_ingest": [r"\bingest\s+(.+)", r"\badd\s+to\s+wiki\s*:?\s*(.+)",
                    r"\bimport\s+(?:into\s+wiki\s*:?\s*)?(.+)"],
    "wiki_query": [r"\bquery\s*:\s*(.+)", r"\bwiki\s*:\s*(.+)",
                   r"\bwhat\s+does\s+(?:my\s+)?wiki\s+(?:say|know)\s+about\s+(.+)",
                   r"\bsearch\s+(?:my\s+)?wiki\s+(?:for\s+)?(.+)"],
    "wiki_lint": [r"^lint(?:\s+wiki)?\s*$", r"^check\s+wiki\b", r"\bwiki\s+health\b"],
    "creds": [r"^store\s+(?:these\s+)?(?:credentials?|keys?)\b",
              r"^(?:save|keep|take\s+care\s+of)\s+(?:these\s+)?(?:keys?|credentials?)\b"],
}

def _detect_intent(text: str) -> tuple:
    low = text.lower().strip()
    for pat in _P["creds"]:
        if re.search(pat, low): return "credentials", ""
    for pat in _P["wiki_init"]:
        if re.search(pat, low): return "wiki_init", ""
    for pat in _P["wiki_ingest"]:
        m = re.search(pat, low)
        if m: return "wiki_ingest", m.group(1).strip()
    for pat in _P["wiki_query"]:
        m = re.search(pat, low)
        if m: return "wiki_query", m.group(1).strip()
    for pat in _P["wiki_lint"]:
        if re.search(pat, low): return "wiki_lint", ""
    for pat in _P["direct"]:
        m = re.search(pat, low)
        if m:
            after = text[m.end():].strip().lstrip(":\"'")
            before = text[:m.start()].strip().rstrip(":\"'")
            return "direct_post", (after or before).strip() or text
    for pat in _P["tweet"]:
        m = re.search(pat, low)
        if m:
            after = text[m.end():].strip().lstrip(":\"'")
            return "tweet", after.strip() if after.strip() else text
    return "general", text


def _receive_files(files):
    """Copy dropped files to raw/ or detect credential screenshots."""
    import shutil
    from credential_store import is_image
    if not files: return gr.update()
    flist = files if isinstance(files, list) else [files]
    paths = [Path(str(f)) for f in flist]
    # If ALL files are images, could be credentials — let user confirm
    if all(is_image(p) for p in paths):
        return gr.update(value="store credentials")
    # Otherwise, copy to raw/ for wiki ingest
    raw_dir = BASE_DIR / "raw" / "articles"
    raw_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for src in paths:
        try: shutil.copy2(str(src), str(raw_dir / src.name)); names.append(src.name)
        except Exception: pass
    return gr.update(value=f"ingest {names[0]}") if names else gr.update()


def _clean_tweet(raw): return __import__("post_flows").clean_tweet(raw)


def _post_tweet_text(text: str) -> str:
    from twitter_post import check_twitter_ready, post_tweet
    if not check_twitter_ready(): return "**Error:** Twitter credentials not set."
    result = post_tweet(text.strip())
    if result.get("success"):
        tid = result.get("tweet_id", "")
        try: __import__("wiki_engine").log_posted_tweet(text.strip(), tweet_id=tid)
        except Exception: pass
        try: __import__("memory").record_success("tweet_post", "tweepy", f"id:{tid}")
        except Exception: pass
        return f"**Posted.** Tweet ID: {tid}"
    err = result.get("error", "Unknown error")
    try: __import__("memory").record_failure("tweet_post", err)
    except Exception: pass
    return f"**Error:** {err}"


# ─── Main handler: Go button at top ───

def _run_and_fill(intention, files, prev_ctx):
    """5-tuple: (run_status, run_result_grp, agent_result, draft_post_btn, ctx)."""
    _e = ("", _hide(), "", _hide(), None)
    if not intention or not intention.strip():
        yield _e; return
    intention = intention.strip()
    kind, content = _detect_intent(intention)

    if kind == "credentials":
        yield _verb("Reading credentials..."), _hide(), "", _hide(), None
        from credential_store import store_credentials_from_images
        imgs = [Path(str(f)) for f in (files if isinstance(files, list) else [files])] if files else []
        if not imgs:
            yield "Drop credential screenshots first, then hit Go.", _hide(), "", _hide(), None
            return
        msg = store_credentials_from_images(imgs)
        yield msg, _show(), msg, _hide(), None
        return

    if kind == "wiki_init":
        yield _verb("Building wiki..."), _hide(), "", _hide(), None
        msg = __import__("wiki_engine").wiki_init()
        yield msg, _show(), msg, _hide(), None
        return

    if kind == "wiki_ingest":
        yield _verb("Looking for file..."), _hide(), "", _hide(), None
        from wiki_engine import find_raw_file, build_ingest_prompt, save_ingest_result
        fpath = find_raw_file(content)
        if not fpath:
            yield f"**Error:** No file matching '{content}' in raw/.", _hide(), "", _hide(), None
            return
        yield _verb(f"Reading {fpath.name}..."), _hide(), "", _hide(), None
        try:
            result = __import__("agent_backend").generate(build_ingest_prompt(fpath))
        except Exception as e:
            yield f"**Error:** {e}", _hide(), "", _hide(), None; return
        yield _verb("Filing into wiki..."), _hide(), "", _hide(), None
        created = save_ingest_result(fpath, result)
        yield "**Ingested:** " + ", ".join(created), _show(), result, _hide(), None
        return

    if kind == "wiki_query":
        yield _verb("Searching wiki..."), _hide(), "", _hide(), None
        try:
            answer = __import__("agent_backend").generate(
                __import__("wiki_engine").build_query_prompt(content))
        except Exception as e:
            yield f"**Error:** {e}", _hide(), "", _hide(), None; return
        yield _verb("Done."), _show(), answer.strip(), _hide(), {"type": "query", "result": answer.strip()}
        return

    if kind == "wiki_lint":
        yield _verb("Checking wiki health..."), _hide(), "", _hide(), None
        try:
            report = __import__("agent_backend").generate(
                __import__("wiki_engine").build_lint_prompt())
        except Exception as e:
            yield f"**Error:** {e}", _hide(), "", _hide(), None; return
        yield _verb("Report ready."), _show(), report.strip(), _hide(), None
        return

    if kind == "direct_post":
        tweet = _clean_tweet(content)
        if not tweet:
            yield "**Error:** No tweet text found.", _hide(), "", _hide(), None; return
        yield _verb("Posting directly..."), _show(), tweet, _hide(), None
        yield _post_tweet_text(tweet), _show(), tweet, _hide(), None
        return

    if kind == "tweet":
        yield _verb("Drafting tweet..."), _hide(), "", _hide(), None
        try:
            from wiki_engine import build_tweet_prompt
            raw = __import__("agent_backend").generate(build_tweet_prompt(content))
        except Exception as e:
            yield f"**Error:** {e}", _hide(), "", _hide(), None; return
        yield _verb("Sharpening..."), _hide(), "", _hide(), None
        time.sleep(0.5)
        tweet = _clean_tweet(raw)
        if not tweet:
            yield "**Error:** Could not generate tweet.", _hide(), "", _hide(), None; return
        ctx = {"type": "tweet", "result": tweet}
        yield _verb("Draft ready — hit Post to send."), _show(), tweet, _show(), ctx
        return

    # ── General task (or follow-up) ──
    from agent_backend import generate
    if prev_ctx and prev_ctx.get("result"):
        prompt = (f"PREVIOUS RESULT:\n{prev_ctx['result'][:1000]}\n\n---\n\n"
                  f"USER FOLLOW-UP: {intention}\n\n"
                  "Revise the previous result based on the follow-up. "
                  "Output only the revised result. No commentary.\n")
        yield _verb("Refining..."), _hide(), "", _hide(), None
    else:
        prompt = intention
        yield _verb("Thinking..."), _hide(), "", _hide(), None
    try:
        raw = generate(prompt)
    except Exception as e:
        yield f"**Error:** {e}", _hide(), "", _hide(), None; return
    result = raw.strip()
    show_post = _show() if prev_ctx and prev_ctx.get("type") == "tweet" else _hide()
    ctx = {"type": prev_ctx["type"] if prev_ctx else "general", "result": result}
    yield _verb("Done. Type to refine."), _show(), result, show_post, ctx


def _load_css() -> str:
    p = BASE_DIR / "theme.css"
    return p.read_text() if p.exists() else ""


# ─── Build the panel ───

def build_panel() -> "gr.Blocks":
    if gr is None:
        raise ImportError("gradio not installed — run: pip3 install gradio")

    def _post_draft_clicked(draft_text, _ctx):
        print("Post clicked")
        yield _verb("Posting..."), _show(), draft_text, _show(), _ctx
        msg = _post_tweet_text(draft_text)
        yield msg, _show(), draft_text, _hide(), None

    with gr.Blocks(title="OpenClay") as panel:
        gr.Markdown("# *OpenClay*", elem_classes=["app-title"])

        # ══ MAIN INPUT ══
        main_input = gr.Textbox(
            label="", show_label=False,
            placeholder="What do you want to build?",
            lines=4, elem_id="main_input", container=True, scale=1,
            autofocus=True,
        )
        drop_zone = gr.File(
            label="Drop files here — documents, credentials, anything",
            file_count="multiple", elem_classes=["drop-zone"],
        )
        run_btn = gr.Button("Go", variant="primary",
                            elem_classes=["run-btn"])
        run_status = gr.Markdown("", elem_classes=["status-bar"])

        ctx_state = gr.State(None)

        # ══ RESULT AREA ══
        with gr.Group(visible=False,
                      elem_classes=["result-card"]) as run_result_grp:
            gr.Markdown("### Result", elem_classes=["result-heading"])
            agent_result = gr.Textbox(
                label="", lines=6, interactive=True,
                elem_classes=["result-text"],
            )
            draft_post_btn = gr.Button(
                "Post", variant="primary", visible=False,
                elem_classes=["run-btn"],
            )

        # ── Wire: file drop → copy to raw/ and pre-fill input ──
        drop_zone.change(_receive_files, inputs=[drop_zone],
                         outputs=[main_input])

        _out = [run_status, run_result_grp, agent_result, draft_post_btn, ctx_state]
        run_btn.click(_run_and_fill, inputs=[main_input, drop_zone, ctx_state],
                      outputs=_out)
        main_input.submit(_run_and_fill, inputs=[main_input, drop_zone, ctx_state],
                          outputs=_out)
        draft_post_btn.click(_post_draft_clicked, inputs=[agent_result, ctx_state],
                             outputs=_out)

    return panel


def launch(share: bool = False):
    panel = build_panel()
    panel.launch(server_name="127.0.0.1", server_port=7861, share=share,
                 inbrowser=True, show_error=True, css=_load_css(),
                 quiet=True)


if __name__ == "__main__":
    launch()
