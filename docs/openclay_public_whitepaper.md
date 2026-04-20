# OpenClay: A Local-First AI Operating System

**COANA Labs · San Juan, Puerto Rico · v1.0 · April 2026**

---

## Abstract

OpenClay is a local-first AI operating system for personal and professional use. It runs entirely on the user's hardware, maintains persistent memory across sessions, and supports multi-agent orchestration — all without cloud dependency.

Unlike web-based AI assistants, OpenClay has no internet requirement, no subscription, and no data egress. It is designed to work in the places cloud tools fail: during power outages, in data-restricted clinical environments, in bandwidth-constrained regions, and for anyone who has decided their work belongs to them.

OpenClay is MIT-licensed, open source, and free to use in full.

---

## The Problem

Every major AI assistant built in the last three years shares the same architectural assumption: the user's data goes somewhere else.

Cloud AI tools require internet connectivity, send all messages to remote servers, charge per token or per month, and reset context with every new session. For most use cases in well-resourced environments with stable infrastructure, this is invisible friction. For a large and growing set of users, it is a structural failure.

**Who the cloud model fails:**

- **Healthcare workers** in hospitals with strict patient-data policies. Every query about a case, a protocol, or a differential diagnosis that goes through a third-party server is a compliance risk.
- **Researchers** in pharmaceutical, legal, and financial settings where data sovereignty is a contractual or regulatory requirement.
- **Users in infrastructure-constrained regions.** Puerto Rico loses grid power frequently. In the months after Hurricane María, large portions of the island had no internet for weeks. A tool that requires a server in Virginia to think is not a tool — it's a dependency.
- **Students and independent practitioners** who cannot afford $20–$200/month for tools their better-funded peers take for granted.

The KnowYou-Bench study (Zhejiang University, Apple, Tencent — arXiv:2604.08455, April 2026) quantified a failure mode that practitioners already knew intuitively: even frontier models drop to **44% success on context-dependent tasks** — because they don't know the user. The same model that can write a legal brief from scratch cannot remember that you are a paralegal in Puerto Rico who works in Spanish, prefers bullet summaries, and has been refining the same contract clause for six weeks.

The failure isn't intelligence. It's memory. And it's architectural.

---

## The Memory Gap

The KnowYou-Bench result points to a specific gap: models that are powerful in the general case collapse on the personal case. The reason is that "knowing the user" requires persistent, structured memory — and no cloud tool has solved this, because it requires trusting a third party with everything that makes you you.

OpenClay solves it with a three-layer memory architecture that runs entirely on the user's machine.

### Layer 1: SOUL.md — Persistent Identity

`SOUL.md` is a plain-text file in the project root. It contains whatever the user wants Clay to know permanently: who they are, what they work on, how they prefer to communicate, what languages they use, what constraints they operate under.

It is read at every session start and injected into every system prompt. It does not expire. It does not reset. It does not require a login.

This is the simplest and most durable form of AI personalization: a file you own, on a disk you control, that tells the model who it's talking to.

### Layer 2: Mem0 — Episodic and Semantic Memory

Mem0 is an open-source memory framework that sits on top of a local vector store (ChromaDB). Every conversation turn — user messages and Clay responses — is processed to extract memories: facts stated, preferences expressed, projects mentioned, decisions made.

These memories are retrieved at query time using hybrid search (semantic similarity + keyword matching) and injected into the context window ahead of the response. The result is a model that, over time, appears to know you — because it does. It knows what you've told it, what it's helped you with before, and what you've been working on.

Memories are stored locally. They are never sent anywhere. The memory store grows as long as you use it, and can be exported, backed up, or deleted at any time.

### Layer 3: Hindsight — Document Knowledge Base

Hindsight is a research memory layer that ingests documents — PDFs, text files, markdown, connected folders — and indexes them for retrieval. When a query is likely to benefit from document context, OpenClay retrieves relevant passages and injects them into the response.

This allows Clay to answer questions about your documents, your projects, and your research without requiring cloud OCR, cloud storage, or any external service.

Together, these three layers form a persistent, compounding knowledge base of the user — the architectural answer to the KnowYou-Bench failure mode.

---

## Architecture

OpenClay is built from five components, all running locally.

### clay_server.py — Python HTTP Backend

The server is a single Python file (~3,000 lines) running a standard `http.server.HTTPServer`. It handles all API routes, manages agent state, coordinates Ollama calls, reads and writes memory, and serves the frontend.

Choosing a single-file Python HTTP server over Flask or FastAPI was deliberate: it installs with zero dependencies beyond Python's standard library, runs on any Python 3.10+ installation, and makes the codebase readable to anyone. There is no framework magic to debug.

### Ollama — Local Model Runtime

[Ollama](https://ollama.ai) provides the model execution layer. It runs entirely on the user's hardware — CPU or GPU. OpenClay auto-detects the best available model at startup based on hardware profile (Apple Silicon, NVIDIA GPU, CPU-only) and selects from a ranked list (llama3, qwen2.5, mistral, gemma, phi3).

Ollama starts automatically when the server launches. The `ensure_ollama_running()` function checks via `ollama list`, spawns `ollama serve` if needed, and waits 3 seconds — all before the HTTP server accepts its first request. A banner in the UI shows "Starting local model…" and auto-dismisses when the model is ready.

### p5.js — The Clay Interface

The frontend is a single HTML file (`index.html`) with a p5.js canvas as the primary interaction surface. The "blob" — a breathing, morphing organic shape — represents the active agent. Its color changes when you switch agents. It pulses when thinking. Responses stream into a stacking conversation thread overlaid on the canvas.

This design was intentional: the interface should feel like a presence, not a form.

### Agent System — Five Specialized Voices

OpenClay ships with five agents defined in YAML configuration files under `agents/`. Each agent has a name, a color accent, a personality description, and a system prompt. Agents are loaded at startup. Switching agents triggers a color morph animation on the blob and changes the active system prompt for all subsequent responses.

### Clay Code — Local File Operations

Clay Code is a code editing interface at `/claycode`. It reads, diffs, and edits files in the working directory. All operations are local. No file content leaves the machine.

---

## The Agent System

**Clay General** — The default. Warm, capable, multilingual. Handles research, drafting, analysis, and general conversation. Uses the full memory stack. Responds in the language you use.

**Clay Investigador** — Research-focused. Direct, systematic, citation-aware. Built for document analysis, literature review, and structured research. Optimized for long-form synthesis.

**Clay Clínico** — Clinical tone. Conservative, precise, evidence-grounded. Designed for healthcare workers who need clear responses that respect the constraints of clinical environments. Does not speculate beyond available evidence.

**Clay Coder** — Engineering voice. Terse, precise, code-first. Optimized for shorter completions (256-token window) to reduce latency on CPU-only hardware.

**Clay Explorer** — Open, generative, lateral. Designed for early-stage ideation, brainstorming, and creative research. Asks questions, proposes frameworks, surfaces unexpected connections.

### Agent Orchestration

The `/api/orchestrate` endpoint chains agents in sequence. A goal is specified; a subset of agents is selected. Each agent receives the original goal, all previous agents' outputs, and Mem0 context relevant to the goal. The result is a multi-perspective analysis from specialized voices — saved to the conversation log and restorable from the projects sidebar.

---

## Clay Code

Clay Code is OpenClay's local coding agent.

**What it does:**
- Reads any file in the working directory
- Proposes edits as diffs before applying them
- Executes code in a sandboxed subprocess
- Displays stdout/stderr in real time
- Maintains context across a session

**What it does not do:**
- Send any file content to a remote server
- Execute code without user confirmation (plan mode available)
- Require any cloud API or external tool

---

## Privacy Model

### What never leaves your machine

- All messages you send to OpenClay
- All responses generated by Clay
- All memories stored by Mem0
- All documents ingested by Hindsight
- Your SOUL.md profile
- Your conversation history and projects
- All files read or edited by Clay Code
- All agent outputs, including orchestration results
- Your hardware profile

### What optionally leaves (nothing by default)

OpenClay has no external calls in its default configuration. The following are available only when explicitly configured by the user:

- **Twitter/X publishing** — requires user-provided OAuth tokens in `.env`
- **Instagram publishing** — requires user-provided Graph API credentials
- **Cloud model fallback** — Anthropic or OpenAI API, if Ollama is unavailable and user provides a key

No telemetry. No analytics. No crash reporting. No usage data of any kind.

---

## The Memory Moat

As software creation costs approach zero and SaaS switching costs collapse, a new pattern emerges: the defensible moat shifts from features to accumulated personal context.

A competitor can clone OpenClay's code. They cannot clone what OpenClay knows about you after a year of use. Every conversation, every preference expressed, every project milestone recorded — these accumulate in a memory store on your hardware that belongs exclusively to you.

This is the inverse of the cloud model. Cloud AI tools own your context. They use it to train their models, improve their products, and build competitive moats on the aggregate of their users' data. If you leave, you take nothing. The relationship resets.

With OpenClay, the memory lives on your machine. It grows with you. It cannot be replicated by a competitor. If you switch tools, you can export it. The longer you use it, the more irreplaceable it becomes — not because of lock-in, but because of genuine accumulated value.

This is what "AI that understands your context" means in practice. Not a model that's generally smart. A model that is specifically smart about *you*.

---

## Puerto Rico Context

OpenClay was built in Puerto Rico, and Puerto Rico shaped its design philosophy in ways that aren't metaphorical.

The island experiences electrical grid instability that is structural, not occasional. After Hurricane María in 2017, parts of Puerto Rico had no power for eleven months. The pharmaceutical manufacturing sector — a core part of the island's economy — operates under FDA data integrity requirements that make cloud AI use legally complex. The University of Puerto Rico system serves students who cannot afford the subscription costs that have become standard for AI-assisted research at mainland institutions.

These are not edge cases. They are the normal conditions under which a significant portion of the world's knowledge workers operate.

**Local-first is not a constraint for Puerto Rico. It is a design philosophy.**

A tool that works offline is a tool that works during a grid failure. A tool that stores data locally is a tool that a pharmaceutical GMP facility can actually use. A tool that costs nothing beyond the hardware you already own is a tool that a student at UPR-Mayagüez can use on the same terms as a researcher at MIT.

The CHAIC (Caribbean Health AI Congress) in September 2026 will bring together healthcare AI practitioners from across the Caribbean. OpenClay's Clay Clínico agent is designed for the use cases that will dominate that conversation: local AI assistance for clinical documentation, evidence review, and administrative workflows — all without patient data leaving the institution.

---

## Roadmap

**Near-term (2026)**
- Windows native support
- Mobile companion app — query Clay from your phone, synced with desktop memory store
- Plugin system for MCP (Model Context Protocol) tools
- Scheduled autonomous tasks — run agent chains on a cron schedule

**Medium-term**
- Clay Clínico expansion — HIPAA-aware memory handling, EHR export format parsing, clinical workflow prompts
- Multilingual agent expansion — Spanish-first UI, Portuguese support, regional language models
- Meshtastic mesh network integration — Clay nodes over LoRa radio when internet is unavailable

**Community**
- Agent marketplace — share custom agent definitions via GitHub
- Memory migration tools — import/export between OpenClay instances
- Model benchmarking suite — evaluate any Ollama model against OpenClay's task set

---

## How to Contribute

OpenClay is MIT-licensed and welcomes contributions.

**GitHub:** [https://github.com/openclay1/OpenClay](https://github.com/openclay1/OpenClay)

**Areas where help is most needed:**
- Windows testing and compatibility
- Multilingual agents and Spanish-first UX
- UI polish — accessibility, mobile layout, animation refinement
- Clay Clínico expansion — clinical prompts, HIPAA-aware memory
- Documentation — user guides, video walkthroughs, translations

Open an issue to discuss larger changes before submitting a PR.

---

## Citation

```
Dávila, F. (2026). OpenClay: A Local-First AI Operating System.
COANA Labs, San Juan, Puerto Rico.
https://github.com/openclay1/OpenClay
```

---

*Built by COANA Labs · San Juan, Puerto Rico*
*"Tools that work in the dark."*
