"""pro/license.py — Local license gate for OpenClay Pro features.

No network call. Checks only for the presence of pro/license.key containing
a non-empty string. Clay Code and future Pro features check is_pro() before
serving their routes.

To activate:
    echo "YOUR_LICENSE_KEY" > pro/license.key
"""
from __future__ import annotations
from pathlib import Path

_KEY_PATH = Path(__file__).parent / "license.key"
_WAITLIST_PATH = Path(__file__).parent / "waitlist.txt"


def is_pro() -> bool:
    """Return True if a non-empty license key file exists."""
    try:
        key = _KEY_PATH.read_text("utf-8").strip()
        return bool(key)
    except Exception:
        return False


def add_to_waitlist(email: str) -> bool:
    """Append an email to the local waitlist file. Returns True on success."""
    email = email.strip()
    if not email or "@" not in email:
        return False
    try:
        from datetime import datetime
        line = f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  {email}\n"
        with open(_WAITLIST_PATH, "a", encoding="utf-8") as f:
            f.write(line)
        return True
    except Exception:
        return False


def gate_html() -> str:
    """Return the paywall HTML page for non-Pro users."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OpenClay Pro</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #0d0d0d;
      color: #ccc;
      font-family: 'JetBrains Mono', 'Courier New', monospace;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
    }
    .card {
      background: #141414;
      border: 1px solid #222;
      border-radius: 12px;
      padding: 48px 40px;
      max-width: 440px;
      width: 100%;
      text-align: center;
    }
    h1 { font-size: 1.4rem; color: #00FF9C; margin-bottom: 12px; font-weight: 600; }
    p { font-size: 0.85rem; color: #888; line-height: 1.7; margin-bottom: 28px; }
    .url { color: #00FF9C; font-size: 0.9rem; margin-bottom: 32px; }
    label { display: block; text-align: left; font-size: 0.75rem; color: #555;
            margin-bottom: 6px; letter-spacing: 0.05em; }
    input[type="email"] {
      width: 100%;
      background: #0d0d0d;
      border: 1px solid #333;
      border-radius: 6px;
      padding: 10px 14px;
      color: #ccc;
      font-family: inherit;
      font-size: 0.85rem;
      outline: none;
      transition: border-color 180ms;
    }
    input[type="email"]:focus { border-color: #00FF9C; }
    button {
      margin-top: 12px;
      width: 100%;
      background: #00FF9C;
      color: #0d0d0d;
      border: none;
      border-radius: 6px;
      padding: 11px;
      font-family: inherit;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 180ms;
    }
    button:hover { opacity: 0.85; }
    #msg { margin-top: 14px; font-size: 0.78rem; color: #00FF9C; min-height: 1.2em; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Clay Code</h1>
    <p>Clay Code is part of OpenClay Pro — a local-first software engineering
    assistant with diff-preview, codebase memory, and git integration.</p>
    <p class="url">openclay.io</p>
    <label for="email">Join the waitlist</label>
    <input type="email" id="email" placeholder="you@example.com" />
    <button onclick="join()">Get Early Access</button>
    <div id="msg"></div>
  </div>
  <script>
    async function join() {
      const email = document.getElementById('email').value.trim();
      if (!email) return;
      const res = await fetch('/api/pro/waitlist', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({email})
      });
      const data = await res.json();
      document.getElementById('msg').textContent = data.ok
        ? 'Added. We will reach out when Pro opens.'
        : 'Invalid email — try again.';
    }
  </script>
</body>
</html>"""
