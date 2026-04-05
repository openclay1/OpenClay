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

_TWEET_PATTERNS = [
    r"\bpost\s+(?:a\s+)?(?:\w+\s+)*tweet\b",
    r"\bsend\s+(?:a\s+)?(?:\w+\s+)*tweet\b",
    r"\bwrite\s+(?:a\s+)?(?:\w+\s+)*tweet\b",
    r"\btweet\s+(that|about|saying|on|something)\b",
    r"^tweet\s+", r"\bpost\s+(?:to|on)\s+(?:twitter|x)\b",
    r"\btweet\s+on\s+x\b", r"\bpost\s+on\s+x\b",
]
_DIRECT_POST_PATTERNS = [
    r"\bpost\s+this\s+directly\b", r"\btweet\s+this\s+directly\b",
    r"\bpost\s+now\b", r"\btweet\s+now\b",
    r"\bpost\s+immediately\b", r"\btweet\s+immediately\b",
]
_WIKI_INIT_PATTERNS = [
    r"\bbuild\s+(?:my\s+)?wiki\b", r"\bcreate\s+(?:my\s+)?wiki\b",
    r"\binit(?:ialize)?\s+(?:my\s+)?wiki\b", r"\bsetup\s+(?:my\s+)?wiki\b",
]
_WIKI_INGEST_PATTERNS = [
    r"\bingest\s+(.+)", r"\badd\s+to\s+wiki\s*:?\s*(.+)",
    r"\bimport\s+(?:into\s+wiki\s*:?\s*)?(.+)",
]
_WIKI_QUERY_PATTERNS = [
    r"\bquery\s*:\s*(.+)", r"\bwiki\s*:\s*(.+)",
    r"\bwhat\s+does\s+(?:my\s+)?wiki\s+(?:say|know)\s+about\s+(.+)",
    r"\bsearch\s+(?:my\s+)?wiki\s+(?:for\s+)?(.+)",
]
_WIKI_LINT_PATTERNS = [
    r"^lint\s*$", r"^lint\s+wiki\b", r"^check\s+wiki\b",
    r"\bwiki\s+health\b",
]

def _detect_intent(text: str) -> tuple:
    """Returns (kind, content). Kinds: wiki_init, wiki_ingest, wiki_query,
    wiki_lint, direct_post, tweet, general."""
    low = text.lower().strip()
    for pat in _WIKI_INIT_PATTERNS:
        if re.search(pat, low): return "wiki_init", ""
    for pat in _WIKI_INGEST_PATTERNS:
        m = re.search(pat, low)
        if m: return "wiki_ingest", m.group(1).strip()
    for pat in _WIKI_QUERY_PATTERNS:
        m = re.search(pat, low)
        if m: return "wiki_query", m.group(1).strip()
    for pat in _WIKI_LINT_PATTERNS:
        if re.search(pat, low): return "wiki_lint", ""
    for pat in _DIRECT_POST_PATTERNS:
        m = re.search(pat, low)
        if m:
            after = text[m.end():].strip().lstrip(":").lstrip('"').rstrip('"')
            before = text[:m.start()].strip().rstrip(":").rstrip('"')
            content = (after or before).strip()
            return "direct_post", content if content else text
    for pat in _TWEET_PATTERNS:
        m = re.search(pat, low)
        if m:
            after = text[m.end():].strip().lstrip(":").lstrip('"').rstrip('"')
            return "tweet", after.strip() if after.strip() else text
    return "general", text


def _clean_tweet(raw: str) -> str:
    from post_flows import clean_tweet
    return clean_tweet(raw)


def _post_tweet_text(text: str) -> str:
    """Post tweet text directly. Returns status string."""
    from twitter_post import check_twitter_ready, post_tweet
    if not check_twitter_ready():
        return "**Error:** Twitter credentials not set."
    result = post_tweet(text.strip())
    if result.get("success"):
        tid = result.get("tweet_id", "")
        try:
            from wiki_engine import log_posted_tweet
            log_posted_tweet(text.strip(), tweet_id=tid)
        except Exception:
            pass
        try:
            from memory import record_success
            record_success("tweet_post", "tweepy", f"id:{tid}")
        except Exception:
            pass
        return f"**Posted.** Tweet ID: {tid}"
    err = result.get("error", "Unknown error")
    try:
        from memory import record_failure
        record_failure("tweet_post", err)
    except Exception:
        pass
    return f"**Error:** {err}"


# ─── Main handler: Go button at top ───

def _run_and_fill(intention):
    """4-tuple: (run_status, run_result_grp, agent_result, draft_post_btn)."""
    if not intention or not intention.strip():
        yield "", _hide(), "", _hide()
        return
    intention = intention.strip()
    kind, content = _detect_intent(intention)

    # ── Wiki operations ──
    if kind == "wiki_init":
        yield _verb("Building wiki..."), _hide(), "", _hide()
        from wiki_engine import wiki_init
        msg = wiki_init()
        yield msg, _show(), msg, _hide()
        return

    if kind == "wiki_ingest":
        yield _verb("Looking for file..."), _hide(), "", _hide()
        from wiki_engine import find_raw_file, build_ingest_prompt, save_ingest_result
        fpath = find_raw_file(content)
        if not fpath:
            yield (f"**Error:** No file matching '{content}' in raw/. "
                   "Drop your files in the raw/ folder first."),\
                _hide(), "", _hide()
            return
        yield _verb(f"Reading {fpath.name}..."), _hide(), "", _hide()
        prompt = build_ingest_prompt(fpath)
        try:
            from agent_backend import generate
            result = generate(prompt)
        except Exception as e:
            yield f"**Error:** {e}", _hide(), "", _hide()
            return
        yield _verb("Filing into wiki..."), _hide(), "", _hide()
        created = save_ingest_result(fpath, result)
        summary = "**Ingested.** Created:\n" + "\n".join(f"- {c}" for c in created)
        yield summary, _show(), result, _hide()
        return

    if kind == "wiki_query":
        yield _verb("Searching wiki..."), _hide(), "", _hide()
        from wiki_engine import build_query_prompt
        prompt = build_query_prompt(content)
        try:
            from agent_backend import generate
            answer = generate(prompt)
        except Exception as e:
            yield f"**Error:** {e}", _hide(), "", _hide()
            return
        yield _verb("Done."), _show(), answer.strip(), _hide()
        return

    if kind == "wiki_lint":
        yield _verb("Checking wiki health..."), _hide(), "", _hide()
        from wiki_engine import build_lint_prompt
        prompt = build_lint_prompt()
        try:
            from agent_backend import generate
            report = generate(prompt)
        except Exception as e:
            yield f"**Error:** {e}", _hide(), "", _hide()
            return
        yield _verb("Report ready."), _show(), report.strip(), _hide()
        return

    # ── Tweet / post operations ──
    if kind == "direct_post":
        tweet = _clean_tweet(content)
        if not tweet:
            yield "**Error:** No tweet text found.", _hide(), "", _hide()
            return
        yield _verb("Posting directly..."), _show(), tweet, _hide()
        msg = _post_tweet_text(tweet)
        yield msg, _show(), tweet, _hide()
        return

    if kind == "tweet":
        yield _verb("Drafting tweet..."), _hide(), "", _hide()
        try:
            from agent_backend import generate
            from wiki_engine import build_tweet_prompt
            raw = generate(build_tweet_prompt(content))
        except Exception as e:
            yield f"**Error:** {e}", _hide(), "", _hide()
            return
        yield _verb("Sharpening..."), _hide(), "", _hide()
        time.sleep(0.5)
        tweet = _clean_tweet(raw)
        if not tweet:
            yield "**Error:** Could not generate tweet.", _hide(), "", _hide()
            return
        yield _verb("Draft ready — hit Post to send."), _show(), tweet, _show()
        return

    # General task
    yield _verb("Thinking..."), _hide(), "", _hide()
    try:
        from agent_backend import generate
        raw = generate(intention)
    except Exception as e:
        yield f"**Error:** {e}", _hide(), "", _hide()
        return
    yield _verb("Done."), _show(), raw.strip(), _hide()


def _load_css() -> str:
    p = BASE_DIR / "theme.css"
    return p.read_text() if p.exists() else ""


# ─── Build the panel ───

def build_panel() -> "gr.Blocks":
    if gr is None:
        raise ImportError("gradio not installed — run: pip3 install gradio")

    def _post_draft_clicked(draft_text):
        """Post the already-drafted tweet. No regeneration."""
        print("Post clicked")
        yield _verb("Posting..."), _show(), draft_text, _show()
        msg = _post_tweet_text(draft_text)
        yield msg, _show(), draft_text, _hide()

    with gr.Blocks(title="OpenClay") as panel:
        gr.Markdown("# *OpenClay*", elem_classes=["app-title"])

        # ══ MAIN INPUT ══
        main_input = gr.Textbox(
            label="", show_label=False,
            placeholder="What do you want to build?",
            lines=4, elem_id="main_input", container=True, scale=1,
            autofocus=True,
        )
        run_btn = gr.Button("Go", variant="primary",
                            elem_classes=["run-btn"])
        run_status = gr.Markdown("", elem_classes=["status-bar"])

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

        # ── Wire: main Go ──
        run_btn.click(
            _run_and_fill, inputs=[main_input],
            outputs=[run_status, run_result_grp, agent_result,
                     draft_post_btn],
        )
        main_input.submit(
            _run_and_fill, inputs=[main_input],
            outputs=[run_status, run_result_grp, agent_result,
                     draft_post_btn],
        )

        # ── Wire: draft Go (post without regeneration) ──
        draft_post_btn.click(
            _post_draft_clicked, inputs=[agent_result],
            outputs=[run_status, run_result_grp, agent_result,
                     draft_post_btn],
        )

    return panel


def launch(share: bool = False):
    panel = build_panel()
    panel.launch(server_name="127.0.0.1", server_port=7861, share=share,
                 inbrowser=True, show_error=True, css=_load_css(),
                 quiet=True)


if __name__ == "__main__":
    launch()
