# Changelog

## v1.0.0 — 2026-04-07

### Added
- ClayRuntime execution wrapper (agent.py) — sanitize → gate → execute → validate
- input_guard.py — prompt injection defense, security_log.md
- permissions.py — GREEN/YELLOW/RED tier gates, strict mode
- retry_ext.py — exponential backoff, known_errors.json pattern matching
- watchdog.py — module health monitoring, auto-restart, healing_log.md
- self_improver.py — recurring issue detection and targeted improvement
- browser_agent.py — Playwright browser control with ClayRuntime wiring
- model_router.py — 3-tier routing: gemma4:e4b (LOCAL_FAST) → gemma4:26b (LOCAL_SMART) → Claude (CLOUD)
- mobile_bridge.py — WebSocket + HTTP server, QR code access, voice input, file upload
- self_build_loop.py — backup-first, test-gated, rollback-capable autonomous improvement
- static/mobile.html — full mobile web app over local WiFi
- SOUL.md — identity, purpose, and survival contract
- AGENTS.md — locked file list and safe build contract
- QUICKSTART.md — first-time user setup guide
- Gemma 4 E4B and 26B as primary local model tiers (Apache 2.0, no API dependency)

### Changed
- agent.py — full ClayRuntime integration across run_loop()
- panel.py — Mobile accordion section, QR codes, "Improve OpenClay" button
- app.py — daemon threads for watchdog, mobile_bridge, self_improver
- README.md — rewritten in first person by OpenClay

### Architecture
- 21 self_tests across all modules, all passing
- All modules under 300 lines
- Escalation chain: LOCAL_FAST → LOCAL_SMART → CLOUD with automatic fallback
- Full independence from subscription APIs via local Gemma 4 routing

## v0.2.0 — 2026-04-05 (commit a642e56)
Core skeleton — wiki memory, credential intake, Twitter posting, dashboard, Claude Code backend

## v0.1.0 — 2026-04-03 (commit 2ebee66)
Initial commit — core agent skeleton
