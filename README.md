# *OpenClay*

I am a local-first AI agent that runs on your machine, answers to you, and gets better over time. You tell me what you want done — I figure out the rest.

## What I can do

- **Take a single instruction and act on it.** You type, I execute. One input, one button.
- **Detect your hardware and install what's needed.** Ollama, models, tools — silently, no questions.
- **Route tasks through three tiers of intelligence.** Fast local (Gemma 4 e4b), smart local (Gemma 4 26b), and cloud only when both fail.
- **Maintain a wiki that compounds over time.** Ingest files, query knowledge, lint for contradictions. Markdown files you own.
- **Draft and post content.** Tweets, captions, social posts — drafted from intention, posted only with your approval.
- **Accept tasks from your phone.** WebSocket bridge, QR code access, voice input, file uploads — all over local WiFi.
- **Guard every input and output.** Prompt injection detection, permission tiers, output validation. Every flagged input logged.
- **Heal myself.** Retry failed calls, restart broken modules, pattern-match known errors, auto-fix recurring issues.
- **Improve myself.** A constrained self-build loop reads my failure logs, proposes small fixes, tests them, and keeps only what passes.
- **Remember what works.** Persistent memory in AGENTS.md — read before every action, updated after every outcome.

## How to run me

```bash
pip install openclay-agent
```

Or from source:

```bash
git clone https://github.com/openclay1/OpenClay.git
cd OpenClay
pip3 install -r requirements.txt
python3 app.py
```

I will detect your machine, pick the right model, install it, and open a browser panel at `http://127.0.0.1:7861`. Your phone can connect by scanning the QR code in the Mobile section.

## What makes me different

- **I run entirely on your hardware.** No cloud account required. No data leaves your machine unless you add an API key and I need to escalate. Even then, I ask first.
- **I enforce a strict security contract.** Every action is tagged GREEN (autonomous), YELLOW (logged), or RED (needs your approval). I cannot post, delete, purchase, or run shell commands without your explicit permission. Prompt injections are caught, stripped, and logged before they reach the model.
- **I get better without your help.** My self-build loop reads failure logs, generates a fix under 20 lines, backs up the target file, applies the change, runs all 21 self-tests, and keeps the fix only if every test passes. If any test fails, I roll back automatically. I can only edit five approved files — never my own safety modules.

## Architecture

```
intention → ClayRuntime [guard → permission gate → execute → validate output]
                ↓
    model_router [LOCAL_FAST → LOCAL_SMART → CLOUD]
                ↓
    agent_backend → Ollama (gemma4:e4b / gemma4:26b)
                ↓
    memory ← wiki ← logs ← self_build_loop
```

### Model routing tiers

| Tier | Model | Used for |
|------|-------|----------|
| LOCAL_FAST | `gemma4:e4b` | Formatting, scheduling, captions, hashtags, tweets, file ops, status checks, simple Q&A |
| LOCAL_SMART | `gemma4:26b` | Wiki ingest/query/lint, self-build fixes, code review, summarization, reasoning |
| CLOUD | Claude / GPT-4o | Architecture, multi-step debugging, code gen over 50 lines — only when local fails |

### Permission tiers

| Tier | Behaviour | Examples |
|------|-----------|----------|
| GREEN | Fully autonomous | Read files, wiki ops, local LLM, queue management |
| YELLOW | Auto-execute, logged | Install stack, pull models, read public URLs |
| RED | Blocked until approved | Post tweet, run shell command, delete data, purchase |

### Project structure

```
app.py              — entry point
agent.py            — core loop + ClayRuntime security wrapper
panel.py            — browser UI (Gradio)
agent_backend.py    — switchable LLM backend (Ollama)
model_router.py     — LOCAL_FAST / LOCAL_SMART / CLOUD routing
input_guard.py      — prompt injection detection + sanitization
permissions.py      — GREEN/YELLOW/RED action tiers + domain allowlist
retry_ext.py        — retry decorator (3x, exponential backoff)
watchdog.py         — 4-tier self-healing daemon
self_improver.py    — autonomous improvement loop (24h cycle)
self_build_loop.py  — constrained self-editing (allowlisted files only)
mobile_bridge.py    — phone interface (WebSocket + static + QR + voice)
browser_agent.py    — headless Playwright browser
wiki_engine.py      — wiki: ingest, query, lint
memory.py           — AGENTS.md persistent memory
credential_store.py — vision-based credential intake
twitter_post.py     — tweet posting (Tweepy)
post_flows.py       — social post workflows
vision_caption.py   — image/video captioning
oauth.py            — Instagram OAuth
introspect.py       — hardware detection
selector.py         — profile + tool selection
installer.py        — silent Ollama + tool installation
intake_analysis.py  — archetype detection
known_errors.json   — error patterns + auto-fix commands
```

Every module stays under 300 lines. Every module has a `self_test()`. All 21 pass.

Built locally. Runs quietly. Gets better slowly. Answers to you.

## License

MIT — it's yours.

[github.com/openclay1/OpenClay](https://github.com/openclay1/OpenClay)
