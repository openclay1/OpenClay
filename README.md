# *OpenClay*

**Your intention becomes infrastructure.**

OpenClay is a universal local AI bootstrapper. You tell it what you want to do — it detects your hardware, picks the right tools, installs everything silently, takes the first autonomous action, and launches a live panel. No configuration. No tutorials. No consulting.

---

## Quickstart

```bash
# Clone
git clone https://github.com/openclay1/OpenClay.git
cd OpenClay

# Install dependencies
pip3 install -r requirements.txt

# Run
python3 app.py
```

OpenClay will detect your hardware, ask up to 3 questions, set up your stack, and open a Gradio panel at `http://127.0.0.1:7861`.

---

## How It Works

```
You say what you want
        ↓
  Hardware detection (introspect.py)
        ↓
  3-exchange conversational intake (intake.py)
        ↓
  Profile + tool selection (selector.py)
        ↓
  Silent installation (installer.py)
        ↓
  First autonomous action (first_action.py)
        ↓
  Live Gradio panel (panel.py)
```

### Profiles

| Profile      | Who it's for                        | What it builds                         |
|-------------|-------------------------------------|----------------------------------------|
| **Creator** | Content creators, social managers    | Content pipeline, captions, scheduling |
| **Researcher** | Academics, analysts, knowledge workers | Knowledge base, document ingestion   |
| **Operator** | Business owners, automation seekers | Workflow automation, task pipelines     |
| **Builder** | Developers, makers                   | Project scaffold, dev environment       |

---

## Agent Backend Architecture

OpenClay supports two switchable agent engines. Set `AGENT_BACKEND` in `.env`:

```bash
# Local-first agent loop with tool use (default)
AGENT_BACKEND=clawcode

# Simple generation via Ollama CLI
AGENT_BACKEND=claudecode
```

### Claw Code Backend (`clawcode`)

Inspired by [Claw Code](https://github.com/instructkr/claw-code) — the open-source, provider-agnostic agent framework. This backend runs a full **tool-use agent loop** over Ollama's `/api/chat` endpoint:

1. Prompt sent to local Ollama model
2. Model can invoke tools: `write_file`, `read_file`, `run_command`, `list_files`
3. Tool results fed back into the conversation
4. Loop iterates up to 5 turns until the model returns a final answer
5. All execution sandboxed to the project directory

**Entirely local. No API keys. No cloud calls. Free.**

```
User prompt → Ollama /api/chat (with tools) → tool call → execute → feed back → repeat → final answer
```

### Claude Code Backend (`claudecode`)

The original simple path — sends prompts to Ollama via subprocess (`ollama run <model>`) with a urllib `/api/chat` fallback. No tool use, just single-turn generation.

### How the switch works

All modules (`agent.py`, `first_action.py`, `*_profile.py`) call a single function:

```python
from agent_backend import generate
result = generate("your prompt here")
```

`agent_backend.py` reads `AGENT_BACKEND` from `.env` and routes to the correct engine. Swap backends anytime by changing one line in `.env` — no code changes needed.

---

## Hardware Tiers

OpenClay auto-detects your machine and selects the right Ollama model:

| Tier        | Requirements                          | Model                            |
|-------------|---------------------------------------|----------------------------------|
| **Large**   | 32GB+ RAM, Apple Silicon or 6GB+ VRAM | `llama3:8b`                      |
| **Medium**  | 16GB+ RAM, Apple Silicon/CUDA/4GB+ VRAM | `qwen2.5:7b`                  |
| **Medium-Low** | 16GB+ RAM, Intel, no dedicated GPU | `qwen2.5:3b-instruct-q4_K_M`    |
| **Small**   | 8GB+ RAM                              | `qwen2.5:1.5b`                  |
| **Template**| Under 8GB                             | No model (template-only mode)    |

---

## Vision-Powered Captions

Drop images into the panel and OpenClay generates Instagram captions automatically using local vision:

1. **Primary:** Ollama `llava` (local, free)
2. **Fallback:** Claude claude-opus-4-5 (if `ANTHROPIC_API_KEY` is set)
3. **Fallback:** GPT-4o (if `OPENAI_API_KEY` is set)
4. **Last resort:** Ollama text-only (no vision, filename-based)

Captions appear in an editable textbox — tweak and hit Post.

---

## Instagram Integration

One-click OAuth via the Gradio panel:

1. Click **Connect Instagram**
2. Authorize in the browser
3. Token saved automatically to `.env`
4. Drop images → auto-caption → Post

Uses Facebook Business Login (Graph API v21.0) with scopes: `pages_show_list`, `pages_read_engagement`, `instagram_basic`, `instagram_content_publish`.

---

## Project Structure

```
app.py                  # Orchestrator (zero business logic)
introspect.py           # Hardware detection
intake.py               # Conversational onboarding (max 3 exchanges)
intake_analysis.py      # Archetype + intent classification
selector.py             # Profile + tool selection
installer.py            # Silent OS-aware installation
agent.py                # Core autonomous loop (queue → execute)
agent_backend.py        # Switchable backend: Claw Code / Claude Code
first_action.py         # First autonomous action
panel.py                # Gradio web UI
theme.css               # Design system (matches landing page)
oauth.py                # Instagram OAuth flow
vision_caption.py       # Image analysis + caption generation
caption_handler.py      # Upload → caption → post workflow
creator_profile.py      # Content creator profile module
researcher_profile.py   # Research profile module
operator_profile.py     # Automation profile module
builder_profile.py      # Builder profile module
reporting.py            # Panel data + status reporting
config.json             # Global configuration
profiles/*.json         # Profile configurations
```

### Module Rules

- Every module stays under **300 lines**
- Modules communicate only through `/queue` folder (JSON) and SQLite
- Zero business logic in `app.py`
- The Anti-Consultant Rule: act, don't ask

---

## Design System

OpenClay uses a full token-based design system defined in `CLAUDE.md` and `theme.css`:

- **Colors:** Dark theme with `--color-primary: #e06438` (warm orange accent)
- **Typography:** Instrument Serif (headings) + Satoshi (body/UI)
- **Components:** Pill buttons, bordered cards, dashed drop zones
- **All values via CSS custom properties** — never hardcoded hex

---

## Configuration

**`.env`** — secrets and backend selection:
```bash
AGENT_BACKEND=clawcode          # or claudecode
INSTAGRAM_APP_ID=...            # Facebook App ID
INSTAGRAM_APP_SECRET=...        # Facebook App Secret
# ANTHROPIC_API_KEY=...         # Optional: Claude vision fallback
# OPENAI_API_KEY=...            # Optional: GPT-4o vision fallback
```

**`config.json`** — global settings:
```json
{
  "demo_mode": false,
  "panel_port": 7861,
  "max_intake_exchanges": 3,
  "confidence_threshold": 0.7,
  "max_module_lines": 300
}
```

---

## Principles

See [AGENT_PRINCIPLES.md](AGENT_PRINCIPLES.md) for the four governing rules:

1. **Anti-Consultant** — never make the user do something the agent can do
2. **OAuth-First** — one-click browser flow for every platform connection
3. **Capability Acquisition** — if a tool is missing, install it silently
4. **No Half-Outputs** — every result must be actionable and complete

---

## License

MIT
