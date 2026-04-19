# OpenClay Security Audit — Session 7

**Date:** 2026-04-19
**Auditor:** Internal review during development
**Scope:** All HTTP routes, subprocess calls, user input handling

---

## Findings

### 1. Unvalidated message length
**Issue:** `/api/ask` accepted messages of arbitrary length, enabling CPU exhaustion via very large inputs.
**Fix applied:** Added `if len(prompt) > 10000: return 400`
**Status:** Fixed

### 2. Orchestrate accepts unknown agent names
**Issue:** `/api/orchestrate` would silently skip unknown agent names, but a crafted request could probe internal state.
**Fix applied:** Whitelist validation — only names in `_agents` dict are accepted. Empty result after filtering returns 400.
**Status:** Fixed

### 3. Subprocess usage (code execution sandbox)
**Issue:** `/api/execute` runs user-provided Python and Bash code. This is intentional (sandbox feature), but runs without container isolation.
**Mitigations in place:** 30-second timeout, runs in a temp directory, no network access enforced at OS level (future: use `firejail` or Docker).
**Status:** Accepted risk — document clearly in README

### 4. Missing Content-Security-Policy on HTML responses
**Issue:** HTML pages served without CSP allowed arbitrary inline scripts and external resources.
**Fix applied:** `Content-Security-Policy` header added to HTML responses via `_send_csp_headers()`.
**Status:** Fixed

### 5. License key not length-limited
**Issue:** `/api/activate-pro` could accept arbitrarily long strings.
**Fix applied:** Key truncated to 100 chars via `str(key)[:100]`.
**Status:** Fixed

### 6. .env / license.json exposure
**Issue:** `.env` and `~/.openclay/license.json` must never be committed.
**Mitigation:** `.env` is in `.gitignore`. `~/.openclay/` is outside the repo root (home directory).
**Status:** Safe by design

---

## Not in scope (future sessions)
- Container isolation for sandbox execution
- Rate limiting on all endpoints
- CSRF protection (low risk for localhost-only tool)
- Audit logging of Pro activation attempts

---

*This is an internal development audit, not a formal penetration test.*
