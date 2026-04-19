# OpenClay — Public Whitepaper

**Version 1.3 · COANA Labs · Puerto Rico**

---

## Abstract

OpenClay is a fully local, privacy-preserving AI assistant built for professionals who cannot afford to send their data to the cloud. It runs entirely on commodity hardware — from a Mac Mini to a Windows desktop — with no API keys, no subscription, and no data ever leaving the machine. This document describes the system architecture, design principles, and intended use cases.

---

## 1. The Problem

Modern AI assistants require sending every query to a remote server. For clinicians, researchers, and small business owners in regions with unreliable internet — or for anyone who handles sensitive data — this creates an insurmountable trust problem. HIPAA, GDPR, and basic data hygiene demand that patient records, proprietary research, and business documents never leave a controlled environment.

Existing local AI solutions require significant technical expertise to set up and lack the polished interfaces that make cloud AI products usable. OpenClay closes this gap.

---

## 2. Design Principles

1. **Zero egress.** No data of any kind leaves the user's machine during normal operation.
2. **Works offline.** The full feature set functions without internet after initial model download.
3. **Human-centered interface.** The clay blob metaphor — an organic, morphing shape — communicates AI state without intimidating technical jargon.
4. **Multi-agent by design.** Different cognitive tasks require different personas, memory strategies, and tool access.
5. **Honest constraints.** The system acknowledges hardware limits and sets accurate expectations.

---

## 3. Architecture

### 3.1 Runtime Stack

```
User Browser (index.html)
        ↕ HTTP (localhost:3000)
clay_server.py  (Python HTTPServer)
        ↕ HTTP (localhost:11434)
Ollama  (local LLM runtime)
        ↕ GGUF model files
models/ (disk)
```

All communication is local loopback. The browser never makes external requests during inference.

### 3.2 Agent System

OpenClay ships with five default agents, each configured via a JSON file in `agents/`:

| Agent | Color | Specialty |
|---|---|---|
| Clay General | Orange `#e06438` | General conversation |
| Clay Investigador | Purple `#7C3AED` | Research + synthesis |
| Clay Clínico | Teal `#0891B2` | Clinical decision support |
| Clay Explorer | Green `#059669` | Data exploration |
| Clay Coder | Green `#00FF9C` | Code generation + review |

Each agent carries a system prompt, memory backend configuration, and optional workflow templates.

### 3.3 Memory Architecture

OpenClay uses a four-layer memory system:

1. **Session history** — in-memory conversation turns, cleared on restart
2. **Procedural memory (Mem0)** — structured facts extracted from conversations, persisted to disk
3. **Hindsight memory** — research insights indexed by topic, agent-specific
4. **Wiki** — auto-generated knowledge pages from conversation content

### 3.4 Autonomous Task Engine

The task engine decomposes natural language goals into executable steps using a planner-executor loop:

1. LLM generates a structured step list from the goal
2. Each step is executed via the sandbox (Python/Bash subprocess)
3. Results are fed back to the LLM for the next step
4. Final output is written to `sandbox/output/`

Tasks run in a background thread and can be monitored via the settings panel.

---

## 4. Hardware Requirements

| Configuration | RAM | Expected Response Time |
|---|---|---|
| Apple Silicon (M1/M2/M3) | 8 GB+ | 3–8 seconds |
| GPU (NVIDIA 8GB+) | 16 GB RAM | 2–5 seconds |
| CPU-only (x86) | 16 GB RAM | 20–40 seconds |

The default model (`qwen2.5:3b`) runs on any configuration above. Larger models are recommended where hardware permits.

---

## 5. Privacy Model

- All inference runs in the local Ollama process
- Conversation history is stored in signed, hash-chained log files in `logs/`
- Memory is stored in `memory_store/` — never synchronized
- No telemetry, crash reporting, or usage analytics of any kind
- The Gradio footer and any external resource loads are disabled

---

## 6. The Memory Gap

In April 2026, researchers from Zhejiang University, Apple, and Tencent published KnowU-Bench, an evaluation framework for personalized mobile agents (arXiv:2604.08455). Their findings are unambiguous: even frontier models like Claude Sonnet 4.6 drop below 50% success rate on tasks requiring personal context. The core bottlenecks identified are preference acquisition and intervention calibration — not GUI navigation, not reasoning capability.

OpenClay's architecture addresses this gap directly. SOUL.md functions as a persistent user identity layer — a document the user writes once and that travels into every system prompt, giving the model a stable sense of who it is talking to. Mem0 provides episodic and semantic memory with hybrid retrieval, surfacing relevant facts from past conversations at query time. Hindsight indexes the user's own documents and knowledge base, enabling document-grounded answers without cloud indexing. Together, these layers allow OpenClay to perform the preference inference that cloud-based tools structurally cannot — because they reset with every session.

As software creation costs approach zero and SaaS switching costs collapse, the new defensible moat is accumulated personal memory that lives on the user's hardware. OpenClay's memory grows with the user. It cannot be replicated by a competitor because it is the user's own data, history, and context — trained on their work, stored on their machine, owned by them entirely. The longer someone uses OpenClay, the more irreplaceable it becomes.

**Citation:** KnowU-Bench: Evaluating Personalized Mobile Agents. arXiv:2604.08455, April 2026.

---

## 7. Clay Code

Clay Code is the integrated development environment component of OpenClay. It provides:

- A file tree browser connected to the sandbox directory
- Diff view for reviewing changes before committing
- A full conversational interface with the Clay Coder agent
- Git integration (diff, staged, commit) with human approval required before any write operation
- Quick-action prompts: Read a file, Find issues, Write a test

---

## 8. Roadmap

- **v1.4** — Kokoro TTS integration for natural voice output
- **v1.5** — Multi-device mesh networking (Meshtastic integration)
- **v2.0** — Plugin system for custom agent tools
- **v2.1** — Encrypted project export/import

---

## 9. License & Distribution

OpenClay Community Edition is open source under the MIT License.  
OpenClay Pro (Clay Code + grant tools + priority support) is available via Gumroad.

**COANA Labs** · hello@coanalabs.com · Puerto Rico 🇵🇷

*Todo es local. Nada sale de aquí.*
