# CodeMonkeys — Architecture

```
 Browser (any device)                        Fly machine (own app, own volume)
┌──────────────────────┐    HTTPS    ┌──────────────────────────────────────┐
│ static/forge/        │◄──────────► │ server.py (FastAPI, single file)     │
│  index.html  app.js  │  poll 1.5s  │  ├─ auth: PIN+TOTP, HMAC tokens      │
│  swarm.html          │             │  ├─ providers: openai-compat | anthropic
│  🎤 Web Speech API   │             │  ├─ agent loop (thread per message)  │
└──────────────────────┘             │  │   tools → workspace (path-jailed) │
                                     │  │   spawn_agent → Daystrom corps    │
                                     │  ├─ cost governor (tier t0..t3)      │
                                     │  └─ approval gate (risky bash)       │
                                     │ /data: users.json model_config.json  │
                                     │        sessions/*.jsonl workspace/   │
                                     └──────────────────────────────────────┘
                                                  │ git clone/push (GITHUB_TOKEN)
                                                  ▼
                                              GitHub repos
```

## Request flow (one message)

1. `POST /api/sessions/{id}/message` — appends `user` event, starts a daemon thread.
2. Thread runs **agent_loop**: build commander system prompt (doctrine + workspace
   listing) → `call_model` → execute tool calls → feed results back → repeat until
   no tool calls, budget hit, stop flag, or max turns.
3. Every step appends an **event** to the session (also JSONL on /data — an
   immutable, replayable audit log, OpenHands-style).
4. Frontend polls `GET /events?after=N` every 1.5 s while running.

## Event types

`user · text · tool · tool_result · agent_start · agent_end · cost ·
approval · approval_result · error · done` — each `{i, ts, type, ...}`,
subagent events carry `agent`.

## Provider abstraction

History is provider-agnostic (`user / assistant+tool_calls / tool`) and converted
per call: OpenAI-compatible chat-completions (`tools→function`, works for Gemini,
OpenRouter, DeepSeek, xAI, …) or native Anthropic Messages
(`tool_use`/`tool_result` blocks, via the `anthropic` SDK). Adding a provider =
one config entry in the UI, zero code.

## Daystrom corps integration

`corps/agents/*.md` (YAML frontmatter: name/description/tools/model) parsed at
boot. `spawn_agent(agent, task)`:
- maps frontmatter tools → runtime tools (Read→read_file…, allowlist enforced)
- routes model by tier: haiku→t0, sonnet→t1, opus→t3 (or explicit `model-tier`),
  picks the enabled provider nearest that tier (**cost governor**)
- runs a nested loop (depth 1 max, 8 spawns/session max — Campaign cap), returns
  the agent's final report to the commander.
Doctrine (echelons, treasury/reserve, verify gates) is summarized in the
commander system prompt; the full docs are vendored in `corps/`.

## Safety

- **Path jail**: every file tool resolves inside `WORKSPACE_DIR` (realpath check).
- **Approval gate**: bash matching `git push | fly … | rm -rf | git reset --hard |
  git clean | gh repo delete | sudo` blocks on a threading.Event until the user
  approves in the UI (1 h timeout → deny).
- **Budget**: loop halts at `SESSION_BUDGET_USD`; every call emits a cost event.
- **Fail-closed auth**: all API routes require Owner token except register/login.

## Roadmap hooks (designed-in, not yet built)

- **LSP/lint feedback loop** (OpenCode pattern): run `ruff`/`tsc --noEmit` after
  edits, inject diagnostics — slot into `make_executor`.
- **Free-backend bridges**: GitHub Copilot OpenAI-compatible endpoint via device
  flow token exchange; CLI delegation (run OpenCode/Aider as a subprocess tool).
- **Architect mode** (Aider pattern): t3 plans, t0 executes.
- **Parallel subagents**, worktree isolation per agent.
