# Changelog

## v1.2.1 — 2026-04-12

### Added
- Context bloat fix: 3-file boot load (SOUL.md, BRAIN.md, boot_load_policy.md), all others on demand
- confusion_reset.py — intercepts on second failure, plain-language bilingual check-in
- Auto-save with timestamp, crash recovery, session restore ("Tu sesion pauso...")
- Streaming responses via _stream_output() — characters arrive incrementally, not as block
- Voice input redesign: "🎤 Hablar con OpenClay" button, editable field, never auto-submits
- Puerto Rican Spanish + code-switching support in voice transcription
- PersonaPlex detection with graceful fallback on Mac
- network_sandbox.py — blocks external calls without explicit permission per DeepMind 2026 findings
- Local mode fully functional with zero internet (verify_local_mode)
- memory_layer.py — Mem0 local memory backend via Ollama, BRAIN.md fallback
- Idle monitor background thread: processes files + compresses after 10min idle
- "↩ Start this step over" reset button on every output panel
- boot_load_policy.md — defines which context loads for which task type
- /context/ subfolder for on-demand context files

### Changed
- openclay_app.py — streaming output, confusion_reset integration, session restore on boot
- voice_input.py — BUTTON_LABEL, LISTENING_LABEL, TOOLTIP, editable result, never auto-submit
- vibe_brain.py — boot_load(), load_on_demand(), idle_monitor thread, start_idle_monitor()
- requirements.txt — added mem0ai

### Architecture
- 159 assertions across 15 modules, all passing
- All modules under 300 lines
- New test coverage: #50 (boot load), #51-52 (confusion/restore), #53 (streaming),
  #54 (PersonaPlex), #55-56 (network sandbox), #57 (Mem0), #58-59 (idle monitor)

## v1.2.0 — 2026-04-12

### Added
- Trust onboarding: 4-screen first-launch flow with ChatGPT comparison (first_screen.py)
- 7 daily agents: clinical_notes, lab_deviation, vet_soap, research_grant, admin_relief, accounting_audit, medical_billing (daily_agents.py)
- Trust footer on ALL agent outputs: Fuente/Modelo/Timestamp/Confianza bilingual block
- audit_log.py — one-line-per-run audit trail with monthly auto-archive
- voice_input.py — SpeechRecognition + Whisper local transcription + PersonaPlex future layer
- openclay_icon.py — Pillow-generated 512x512 app icon
- biotech_review_agent.py — local literature review with gap analysis
- Build scripts: build_mac_app.sh, build_dmg.sh, build_windows_exe.bat
- HUMAN_INTEGRATION_MANUAL.md (EN + ES) + DESK_CARD_PRINT.md
- Research profiles: oncology, pharma, engineering, veterinary, medical_billing (model_config.py)
- MedGemma 4B auto-recommendation when medical software detected
- Ollama hidden management: auto-start/stop, user never sees terminal
- Zotero PDF watcher + Obsidian YAML frontmatter output (integration_detector.py)
- Idle-time auto-processing in vibe_brain.py (after 10min idle)
- GRANT_EXHIBIT_A.md
- workflow_simulator.py — 17-step clinical/pharma/vet/grant workflows

### Changed
- integration_detector.py — expanded from 13 to 35+ detection targets (hospital, pharma, vet, research, engineering, accounting)
- model_config.py — 5-tier hardware-aware selection (1.5B → 35B Q8), research profile auto-config
- predict_engine.py — removed tweet category (9 groups, was 10)
- SOUL.md — added self-improvement + hidden internals principles
- requirements.txt — pinned versions with Spanish comments

### Architecture
- 103 assertions across 11 modules, all passing
- All modules under 300 lines
- Memory: L0 (SOUL.md) → L1 (BRAIN.md) → L2 (SESSION.md) → L3 (DECISIONS.md)
- Bilingual ES/EN throughout all outputs, UI strings, and documentation

## v1.1.0 — 2026-04-08

### Added
- vibe_brain.py — plain markdown memory (BRAIN.md, SESSION.md, DECISIONS.md)
- Vibe Brain compression cycle: every 10 tasks, SESSION → BRAIN, trimmed to 500 words
- "Why not cloud agents?" positioning in README
- Industries section: healthcare, finance, operations, research
- Conversational first screen: "What are we working on?" with starter actions
- Daily Work section: 6 common task buttons
- Local Success section: wiki pages, queued tasks, self-builds, artifacts
- QUICKSTART.md first-time user guide

### Changed
- wiki_engine.py — query retrieval now uses L0-L3 memory context instead of keyword matching
- wiki_engine.py — query now loads Vibe Brain context first, skips wiki if covered
- panel.py — conversational greeting, Twitter moved to optional accordion
- README.md — daily utility positioning, Twitter clearly optional
- 22 self_tests (was 21), all passing

### Architecture
- Memory: L0 (SOUL.md) → L1 (BRAIN.md) → L2 (SESSION.md) → L3 (DECISIONS.md)
- No external dependencies — plain markdown files, no chromadb/embeddings
- Token target: under 2,000 tokens loaded per task by default

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
