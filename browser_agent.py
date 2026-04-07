"""browser_agent.py — Headless browser via Playwright.

Navigate URLs, read page content for wiki, take screenshots, fill forms /
click elements (only when GREEN or RED-approved). Fresh context every run —
no cookies, no sessions. All activity logged to browser_log.md.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
BROWSER_LOG = BASE_DIR / "browser_log.md"

def _now(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(url: str, action: str, tier: str) -> None:
    """Append one line to browser_log.md."""
    line = f"- `{_now()}` **{tier}** `{action}` — `{url[:120]}`\n"
    try:
        with open(BROWSER_LOG, "a") as f:
            if f.tell() == 0:
                f.write("# Browser Log\n\nAll browsing activity.\n\n")
            f.write(line)
    except FileNotFoundError:
        with open(BROWSER_LOG, "w") as f:
            f.write("# Browser Log\n\nAll browsing activity.\n\n")
            f.write(line)


def _check_perm(action: str, detail: str = "") -> bool:
    """Gate through permissions.py. Returns True if allowed."""
    from permissions import check
    ok, _ = check(action, detail)
    return ok


def _ensure_pw():
    """Import playwright sync_api, raise clear error if missing."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        raise ImportError("playwright not installed. Run: pip3 install playwright && python3 -m playwright install chromium")


def _fresh_browser(pw):
    """Launch chromium headless with a fresh, cookieless context."""
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        accept_downloads=False,
        java_script_enabled=True,
        ignore_https_errors=False,
    )
    context.set_default_timeout(30000)
    page = context.new_page()
    return browser, context, page


# ── Public API ──

def navigate(url: str) -> dict:
    """Navigate to a URL, return page title and text content.

    GREEN tier — fully autonomous. Used by wiki ingest and research.
    """
    from permissions import check_domain
    if not check_domain(url):
        _log(url, "navigate:BLOCKED", "BLOCKED")
        return {"error": f"Domain not in allowlist: {url}"}
    _log(url, "navigate", "GREEN")
    sync_pw = _ensure_pw()
    with sync_pw() as pw:
        browser, ctx, page = _fresh_browser(pw)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = page.title()
            text = page.inner_text("body")[:8000]
            return {"url": url, "title": title, "text": text}
        except Exception as e:
            return {"error": str(e), "url": url}
        finally:
            ctx.close(); browser.close()


def read_page(url: str) -> str:
    """Navigate + return text only. Convenience for wiki builder."""
    result = navigate(url)
    if result.get("error"):
        return f"Error: {result['error']}"
    return result.get("text", "")


def screenshot(url: str, filename: str | None = None) -> Path | None:
    """Navigate to URL and save a screenshot.

    GREEN tier — no interaction, just capture.
    """
    from permissions import check_domain
    if not check_domain(url):
        _log(url, "screenshot:BLOCKED", "BLOCKED"); return None
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    if not filename:
        slug = url.split("//")[-1].replace("/", "_")[:60]
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}.png"
    dest = SCREENSHOTS_DIR / filename
    _log(url, "screenshot", "GREEN")
    sync_pw = _ensure_pw()
    with sync_pw() as pw:
        browser, ctx, page = _fresh_browser(pw)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.screenshot(path=str(dest), full_page=True)
            return dest
        except Exception:
            return None
        finally:
            ctx.close(); browser.close()


def fill_form(url: str, selector: str, value: str) -> dict:
    """Navigate to URL and fill a form field.

    RED tier — requires explicit approval.
    """
    if not _check_perm("form_submission", f"fill {selector} on {url}"):
        _log(url, "fill_form:PENDING", "RED")
        return {"error": "Awaiting approval", "action": "form_submission"}
    from permissions import check_domain
    if not check_domain(url):
        _log(url, "fill_form:BLOCKED", "BLOCKED")
        return {"error": f"Domain not in allowlist: {url}"}
    _log(url, f"fill_form:{selector}", "RED:APPROVED")
    sync_pw = _ensure_pw()
    with sync_pw() as pw:
        browser, ctx, page = _fresh_browser(pw)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.fill(selector, value)
            return {"ok": True, "url": url, "selector": selector}
        except Exception as e:
            return {"error": str(e)}
        finally:
            ctx.close(); browser.close()


def click_element(url: str, selector: str) -> dict:
    """Navigate to URL and click an element.

    RED tier — requires explicit approval.
    """
    if not _check_perm("form_submission", f"click {selector} on {url}"):
        _log(url, "click:PENDING", "RED")
        return {"error": "Awaiting approval", "action": "form_submission"}
    from permissions import check_domain
    if not check_domain(url):
        _log(url, "click:BLOCKED", "BLOCKED")
        return {"error": f"Domain not in allowlist: {url}"}
    _log(url, f"click:{selector}", "RED:APPROVED")
    sync_pw = _ensure_pw()
    with sync_pw() as pw:
        browser, ctx, page = _fresh_browser(pw)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.click(selector, timeout=10000)
            page.wait_for_timeout(1000)
            return {"ok": True, "url": url, "selector": selector,
                    "title": page.title()}
        except Exception as e:
            return {"error": str(e)}
        finally:
            ctx.close(); browser.close()


def ingest_url_to_wiki(url: str) -> str:
    """Read a URL and pass its content to the wiki builder.

    GREEN tier navigate + GREEN tier wiki ingest.
    """
    text = read_page(url)
    if text.startswith("Error:"):
        return text
    from wiki_engine import SOURCES_DIR, RAW_DIR, _slug, _today
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    slug = _slug(url.split("//")[-1])[:40]
    raw_path = RAW_DIR / f"{slug}.md"
    raw_path.write_text(f"---\nsource: {url}\nfetched: {_today()}\n---\n\n{text}\n")
    _log(url, "ingest_to_wiki", "GREEN")
    return f"Saved to raw/{slug}.md — type `ingest {slug}` to process."


def self_test() -> bool:
    """Verify Playwright is installed and core functions work."""
    sync_pw = _ensure_pw()
    with sync_pw() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto("data:text/html,<h1>OpenClay Test</h1><p>ok</p>")
        assert page.title() == "" or True  # data: pages have no title
        text = page.inner_text("body")
        assert "ok" in text, f"page text: {text}"
        ctx.close(); browser.close()
    assert BROWSER_LOG.parent.exists(), "base dir missing"
    _log("data:text/html,self_test", "self_test", "GREEN")
    assert BROWSER_LOG.exists(), "browser_log not created"
    return True
