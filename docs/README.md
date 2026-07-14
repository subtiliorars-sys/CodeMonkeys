# CodeMonkeys docs index

Start on demand. Forge UI work: read **[FORGE_HYGIENE.md](FORGE_HYGIENE.md)** first.

## Jump-in
| Doc | What it is |
|-----|------------|
| [STATE.md](STATE.md) | Current deployment + wave status (read first when resuming) |
| [SETUP.md](SETUP.md) | Fly + local dev walkthrough |
| [ARCHITECTURE.md](ARCHITECTURE.md) | `server.py` ↔ `static/forge/` map |
| [RECOVERY.md](RECOVERY.md) | Lockout + volume recovery |
| [`../WAVES.md`](../WAVES.md) | Automation wave registry |
| [`../OFFICE_HOURS.md`](../OFFICE_HOURS.md) | Worker schedule + playtest URLs |

## Forge lane (`forge-streaming`)
| Doc | What it is |
|-----|------------|
| [FORGE_HYGIENE.md](FORGE_HYGIENE.md) | **Maintainer checklist** — paths, Tailwind build, streaming flags, verify |
| [TERMINAL_DESIGN.md](TERMINAL_DESIGN.md) | Web terminal (default OFF) |
| design/[N12-model-catalog.md](design/N12-model-catalog.md) | Model catalog spec |
| design/[N8-context-compaction.md](design/N8-context-compaction.md) | Context compaction |
| design/[PER_USER_ISOLATION.md](design/PER_USER_ISOLATION.md) | Per-user isolation direction |

## Credits & backlog
| Doc | What it is |
|-----|------------|
| [VERTEX_GCP_CREDITS.md](VERTEX_GCP_CREDITS.md) | Vertex burn hook for batch jobs |
| [IDEATION.md](IDEATION.md) | Product ideation queue |
| [ANTIGRAVITY_BACKLOG.md](ANTIGRAVITY_BACKLOG.md) | Antigravity integration backlog |
| [CODE_GREMLINS.md](CODE_GREMLINS.md) | Known gremlins / triage |
| [RELEASE_NOTES.md](RELEASE_NOTES.md) | Shipped changelog notes |

## Other
| Doc | What it is |
|-----|------------|
| [FRIENDS_ANDROID.md](FRIENDS_ANDROID.md) | Friends Android experiment |
| [`../SECURITY.md`](../SECURITY.md) | Security canon — owner-gated edits |

**Executor rule:** When `WAVES.md` Active queue is empty, update hygiene docs only; do not start owner-gated deploy or OAuth work.
