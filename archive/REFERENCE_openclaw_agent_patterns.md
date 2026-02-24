# OpenClaw Agent Architecture Patterns

Reference: [github.com/openclaw/openclaw](https://github.com/openclaw/openclaw) (219k stars, TypeScript, MIT)
Source: Medium article by Bibek Poudel + repo inspection (Feb 2026)

## What It Is

Local AI agent platform. Connects to messaging apps (WhatsApp, Telegram, Slack, Discord, Signal, iMessage, etc.), routes messages through an LLM, and takes real-world actions via tools. Model-agnostic (Claude, GPT, Gemini, Ollama).

## 7 Core Patterns

### 1. Gateway (Orchestration Layer)

Long-lived background process (`systemd`/`launchd`). WebSocket at `ws://127.0.0.1:18789`. Handles routing, sessions, auth, channel connections. The agent runtime is behind it.

**Pattern**: Never expose raw LLM calls to user input. Always put a controlled orchestration process in front that handles routing, queuing, and state management.

Key source: `src/gateway/`, `src/routing/`, `src/sessions/`

### 2. Channel Adapters (Input Normalization)

Each messaging platform (Baileys for WhatsApp, grammY for Telegram, Bolt for Slack, discord.js) gets an adapter that normalizes input into a consistent message object: sender, body, attachments, metadata. Voice notes get transcribed before reaching the model.

**Pattern**: Normalize all inputs before the model sees them. Context quality = output quality.

Key source: `src/whatsapp/`, `src/telegram/`, `src/slack/`, `src/discord/`, `src/channels/`

### 3. Session Serialization (Concurrency Control)

Each agent maintains stateful sessions. Messages within a session are processed **one at a time** via a Command Queue. No parallel execution within a session.

**Pattern**: Serialize execution per session to prevent state corruption and tool conflicts. Concurrency is dangerous when agents share state.

Key source: `src/sessions/`, `src/agents/lanes.ts`

### 4. Agentic Loop (ReAct)

The core loop: context assembly -> model inference -> tool execution -> loop or reply.

```
while True:
    response = llm.call(context)
    if response.is_text(): send_reply(); break
    if response.is_tool_call():
        result = execute_tool(tool_name, tool_params)
        context.add_message("tool_result", result)
```

**Context assembly** builds the prompt from 4 sources:
- Base system prompt (`src/agents/system-prompt.ts`)
- Skills prompt (compact list of eligible skills, not full text)
- Bootstrap context files (workspace-level context, e.g. `AGENTS.md`)
- Per-run overrides

**Inference** enforces model-specific context limits and maintains a compaction reserve (token buffer for response).

**Tool execution** intercepts structured tool calls, runs them, feeds results back. Streams partial responses in real-time.

Key source: `src/agents/pi-embedded-runner.ts`, `src/agents/pi-embedded-subscribe.ts`, `src/agents/context.ts`, `src/agents/compaction.ts`

### 5. Skills (On-Demand Instruction Loading)

A Skill = a folder with `SKILL.md` containing natural-language instructions + tool configs.

```markdown
---
name: github-pr-reviewer
description: Review GitHub pull requests and post feedback
---
# GitHub PR Reviewer
When asked to review a pull request:
1. Use web_fetch to retrieve the PR diff...
```

Critical design: **Skills are NOT injected in full into the system prompt.** Only a compact index (name, description, path) is injected. The model reads the full `SKILL.md` on demand when it decides a skill is relevant. This keeps the base prompt lean regardless of installed skill count.

Skills can be bundled, managed, or workspace-level. Community registry (ClawHub) exists but carries prompt injection risk.

Key source: `src/agents/skills.ts`, `skills/` directory (60+ bundled skills)

### 6. Memory (File-Based Persistence)

No external DB. Plain Markdown files + SQLite.

```
~/.openclaw/workspace/
  AGENTS.md       # agent config + instructions
  SOUL.md         # personality, tone, preferences
  MEMORY.md       # long-term facts ("user prefers concise responses")
  HEARTBEAT.md    # proactive task checklist
  memory/
    2026-02-15.md # daily ephemeral log (append-only)
    2026-02-16.md # daily ephemeral log
```

- Daily logs are **not auto-injected** into context. Retrieved on demand via memory tools.
- When context window fills, **compaction** summarizes older turns (preserves semantics, reduces tokens).
- Retrieval uses embedding-based search via `sqlite-vec` SQLite extension + optional keyword search.

Key source: `src/memory/` (embeddings, search-manager, sqlite-vec, hybrid search, temporal-decay, query-expansion, batch processing)

### 7. Heartbeat (Proactive Scheduling)

Cron-triggered agentic loop (default: every 30 min). Reads `HEARTBEAT.md` checklist, decides if action needed, acts or returns `HEARTBEAT_OK` (suppressed by Gateway).

**Pattern**: Proactive agents need a scheduling mechanism. Instead of only responding to human input, periodically wake the agent and have it evaluate its task list.

Key source: `src/cron/`

## Additional Technical Details (from repo)

| Component | Implementation |
|-----------|---------------|
| **MCP integration** | `src/agents/pi-extensions/` - standard tool layer for external services |
| **Sandbox execution** | `src/agents/sandbox.ts` - Docker/Podman sandboxing for bash tools |
| **Tool policy** | `src/agents/tool-policy.ts` - approval pipeline, allowlists, gating |
| **Subagents** | `src/agents/subagent-*.ts` - spawn child agents with depth limits |
| **Model failover** | `src/agents/model-fallback.ts` - auth profile rotation, cooldown |
| **Compaction** | `src/agents/compaction.ts` - context window management with retry |
| **Tool loop detection** | `src/agents/tool-loop-detection.ts` - prevents infinite ReAct loops |

## Takeaway for Our Project

These patterns map directly to what we build:

| OpenClaw Pattern | Our Equivalent |
|-----------------|----------------|
| Gateway orchestration | `insight_orchestrator.py`, `retrieval_orchestrator.py` |
| Input normalization | Channel adapters in `database_manager` (Telegram -> normalized chunks) |
| Agentic loop / ReAct | LangGraph state machine in `database_retriever` |
| Skills (on-demand prompts) | `*_prompts.py` files loaded per-stage |
| Memory (file-based) | `relationships.json`, `theme_index.json`, `prediction_ledger.json` |
| Heartbeat (proactive) | `scripts/daily_regime_scan.py` (cron-based theme refresh) |
| Context assembly | State objects (`RetrieverState`, `RiskImpactState`) built per-run |
| Compaction | Not yet needed (single-turn pipeline, no long conversations) |
