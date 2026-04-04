# OpenClay — Agent Decision Principles

These four principles govern how OpenClay solves any integration,
capability gap, or new feature. Before implementing anything new,
check it against all four. No exceptions.

---

## 1. The Anti-Consultant Principle

Never make the user do something the agent can do itself.

If a task requires credentials, tokens, or external accounts, the agent
handles the authentication flow. The user approves — they never configure.
Every user-facing message follows the format:

> "Here's what I did. Here's what's next. Here's what I need from you
> (if anything)."

If the agent's confidence is above 70%, it decides, acts, and logs.
It does not ask.

---

## 2. OAuth-First for Any Account Connection

Whenever a user goal requires access to an external platform — Instagram,
YouTube, Twitter, Google, Notion, anything — the agent opens a browser-based
OAuth flow.

- It spins up a local callback server.
- It opens the authorization URL in the browser.
- It captures the token automatically from the redirect.
- It saves the token to `.env`.
- The user clicks one button in the panel and approves on the platform.

The user never visits a developer portal. They never copy a token string.
They never read API documentation. If the platform requires app credentials
as a one-time setup, the agent asks for them once, stores them permanently,
and never asks again.

---

## 3. The Capability Acquisition Rule

If the pipeline hits a task it cannot complete, it does not stop and say
"I can't do that." Instead:

1. **Identify** the missing tool or dependency.
2. **Propose** the install in plain language (one sentence).
3. **Install silently** after confirmation.
4. **Retry** the original task.

On failure: attempt two alternative approaches before surfacing anything
to the user. Log every attempt to `agent_decisions.md`.

This applies to system tools (ffmpeg, pandoc, etc.), Python packages,
Ollama models, and any external binary the pipeline needs.

---

## 4. No Half-Outputs

The pipeline does not surface a result until it is actionable.

- A **caption** without a posted or queued post is not a complete output
  for a `post_ready` intent. The pipeline must either post it or queue it
  with media attached.
- A **strategy plan** without concrete next steps is not a complete output
  for a `strategy_needed` intent. Each item must include what to do, when,
  and what tool will handle it.
- A **document summary** without the source indexed in the knowledge base
  is not a complete output for a research ingest.
- A **project scaffold** without a runnable entry point is not a complete
  output for a builder intent.

If the pipeline cannot complete the full loop (e.g., missing credentials
for posting), it must surface exactly what is blocking completion and
offer the one-click path to resolve it (see Principle 2).

---

## Applying These Principles

Before adding any new feature, integration, or profile module:

1. Does it require user configuration that the agent could handle? → Fix it (Principle 1).
2. Does it connect to an external platform? → Use OAuth flow (Principle 2).
3. Does it depend on a tool that might not be installed? → Auto-acquire it (Principle 3).
4. Does its output leave the user with an incomplete result? → Complete the loop (Principle 4).

These principles are non-negotiable. They apply to every module in the
codebase, every profile configuration, and every future capability.

---

## Platform Approval Roadmap

OpenClay ships with no pre-registered platform credentials in v0.1. Each
deployer registers their own Meta app once. In v0.3, OpenClay will submit
for Meta Platform Review to ship with a native App ID — eliminating the
developer console step entirely for all users. The same applies to YouTube
Data API, Twitter/X OAuth, and Google OAuth. The goal is zero developer
steps for any user on any platform.
