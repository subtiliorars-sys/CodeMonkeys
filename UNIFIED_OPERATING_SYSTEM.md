# Unified Operating System (UOS) — Claude + Gemini Collaboration Framework

**Version:** 2.0 (Enhanced SKA-OS)  
**Created:** 2026-06-12  
**Purpose:** Standardized protocol for Claude and Gemini autonomous agents across all projects  
**Foundation:** Swarm & Kanban Agent Operating System (SKA-OS) — enhanced with safety, logging, and error handling

---

## 🎯 Core Principles

1. **Git-backed state** — All decisions are committed (durable across sessions)
2. **Kanban-driven** — Single source of truth: KANBAN.md
3. **Multi-agent safe** — Immediate status updates prevent collisions
4. **Budget-aware** — Token tracking and escalation
5. **Heartbeat-visible** — Continuous logging so you know the agent is alive
6. **Error-resilient** — Graceful handling of blockers and failures
7. **Generalizable** — Works for any project with minimal setup

---

## 📋 Setup (Per Project)

Every project needs:
```
<project>/
├── KANBAN.md              # State machine (TO DO, WORKING, BLOCKED, DONE)
├── .agent-config.json     # Token budget, escalation rules
└── (standard git repo)
```

---

## 🔄 THE CORE LOOP (Enhanced)

### Phase 0: Health Check (Before every iteration)
```
1. Check token budget: cat ~/.agent-budget.json
   - If < 50k remaining: ESCALATE to user
   - If 0: STOP immediately, commit state, wait for refill
   
2. Write heartbeat to project status:
   echo "$(date -u) — Agent alive, starting iteration" >> ~/fleet/status/<project>.md
```

### Phase 1: Read Board
```
1. cd <worklog-directory>
2. git pull origin master  # Get latest board state
3. cat KANBAN.md | grep -A 5 "^## TO DO"
4. Find highest-priority task WITH NO BLOCKER
   - Priority order: 🔥 HIGH > MEDIUM > LOW
   - Skip if marked [BLOCKER: ...]
   - If ALL tasks blocked: Create issue in ~/fleet/questions.md, wait
```

### Phase 2: Claim Task (Prevent collisions)
```
1. Move task from TO DO → WORKING in KANBAN.md
2. Commit immediately:
   git commit -m "status: claimed <task-name> for execution"
3. This blocks other agents from picking same task
```

### Phase 3: Execute Task
```
1. cd <target-repo>
2. git checkout -b work/<task-slug>
   - Slug rule: lowercase letters, hyphens only, no spaces
   - Example: "omnidesk-phase2-metrics-dashboard" → work/omnidesk-phase2-metrics-dashboard

3. Implement changes per task requirements
4. After each file save: Log progress to heartbeat
   echo "  - Completed: <what you just did>" >> ~/fleet/status/<project>.md
```

### Phase 4: Test & Verify
```
1. Run tests: npm test (or equivalent)
   - If tests pass: Continue to Phase 5
   - If tests fail ONCE: Run sequentially (npm test -- --serial or equivalent)
   - If tests fail TWICE: 
     a) Move task to BLOCKED in KANBAN.md
     b) Document error: Create ~/fleet/questions.md entry
     c) Go back to Phase 1 (pick next task)

2. Manually verify acceptance criteria:
   Read task file, check off each requirement
   If ANY unchecked: Don't move to Phase 5 yet, fix it first
```

### Phase 5: Commit & Push
```
1. Stage ONLY your files:
   git status  # Verify no stray files
   git add <specific-file-1> <specific-file-2> ...  # NOT git add -A or git add .

2. Commit with standard attribution:
   git commit -m "feat: <summary of what you built>
   
   - Specific change 1
   - Specific change 2
   - Specific change 3
   
   Co-Authored-By: <Agent-Name> <noreply@anthropic.com>"

3. Push to feature branch:
   git push origin work/<task-slug>

4. Log completion to heartbeat:
   echo "  ✅ Pushed work/<task-slug>" >> ~/fleet/status/<project>.md
```

### Phase 6: Mark Done
```
1. cd <worklog-directory>
2. Update KANBAN.md:
   Move task from WORKING → DONE
   Add timestamp: "Completed: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

3. Commit:
   git commit -am "status: completed <task-name>"

4. Update heartbeat:
   echo "✅ Task complete. Ready for next iteration." >> ~/fleet/status/<project>.md
```

### Phase 7: Loop
```
Go back to Phase 0 (health check)
```

---

## 🚨 ENHANCED: Error Handling & Escalation

### Test Failures
```
First failure:
  1. Run tests sequentially
  2. If pass: Continue normally
  
Second failure on same task:
  1. Move task to BLOCKED
  2. Document in KANBAN.md: "Blocker: Test failures - <error message>"
  3. Create ~/fleet/questions.md entry with:
     - Task name
     - Error message (full traceback)
     - Attempted fix
     - User action needed
  4. Pick next task (don't spin on same task)
```

### All Tasks Blocked
```
1. Count blocked tasks
2. If > 2 tasks blocked:
   a) Create ~/fleet/questions.md explaining why
   b) Log to heartbeat: "⚠️ Blocker cascade - waiting for user action"
   c) Sleep 60 seconds
   d) Try again (sometimes blockers resolve)
   e) If still blocked: STOP and wait for user
```

### Token Budget Exhausted
```
1. Check: cat ~/.agent-budget.json
2. If tokens_remaining <= 0:
   a) Commit all work immediately
   b) Update KANBAN.md status
   c) Write heartbeat: "⏸️  Token budget exhausted, stopping"
   d) STOP
```

---

## 🔔 ENHANCED: Logging & Heartbeat

Every project has a heartbeat file:
```
~/fleet/status/<project>.md
```

Updated at:
- Start of iteration (Phase 0)
- After claiming task (Phase 2)
- During execution (Phase 3, after major changes)
- After tests (Phase 4)
- After push (Phase 5)
- When done (Phase 6)

Format:
```
## <project-name> — Heartbeat

**Status:** WORKING | BLOCKED | DONE  
**Current Task:** <task-name> (work/<branch>)  
**Last Update:** 2026-06-12T14:35:00Z  
**Budget:** 142k tokens remaining

### Progress Log
- Started task at 14:30
- Implemented metrics endpoint at 14:32
- Tests passing (112/112) at 14:34
- Ready for push at 14:35
```

This lets you see what the agent is doing **right now** without waiting for completion.

---

## 💾 ENHANCED: Context Persistence

Each task in KANBAN.md includes:
```
## Task Name

**Status:** TO DO | WORKING | BLOCKED | DONE
**Priority:** HIGH | MEDIUM | LOW
**Branch:** work/<branch-name>
**Est. Time:** X hours
**Blocker:** None | [reason]

### Acceptance Criteria
- [ ] Thing 1
- [ ] Thing 2
- [ ] Thing 3

### Key Gotchas
- Don't do X (it breaks Y)
- Remember to Z before committing
- Design decision: We chose A over B because...

### Related Tasks
- Task B (dependent on this)
- Task C (similar pattern, check for reuse)

### Prior Attempts
- Attempt 1 (2026-06-11): Failed because... (see git commit abc123)
- Attempt 2 (2026-06-12): Trying different approach...
```

This prevents re-doing failed work and preserves institutional knowledge.

---

## 🧮 ENHANCED: Token Budget Awareness

File: `~/.agent-budget.json`
```json
{
  "service": "gemini | claude",
  "budget_total": 500000,
  "tokens_used": 142000,
  "tokens_remaining": 358000,
  "per_task_budget": 50000,
  "last_reset": "2026-06-12T00:00:00Z",
  "escalation_threshold": 50000
}
```

Agent checks before each task:
```
if tokens_remaining < per_task_budget:
  ESCALATE: "Not enough budget for next task (~50k needed, only {X}k remaining)"
  
if tokens_remaining < escalation_threshold (50k):
  LOG: "Low budget warning - ~1 task remaining before exhaustion"
```

---

## 🔗 Multi-Agent Coordination

When Claude and Gemini work on different projects:

**Never overlap:** Each agent owns distinct repos/projects
- Claude territory: PixelSports, MeniscusMaximus, CodeMonkeys, TradeGame, DrivingMeNuts
- Gemini territory: OmniTender family (omnidesk, omniverse, omnitender-web, etc.)
- Shared: agent-corps, fleet, sea-games

**Cross-project signaling:** If Gemini finishes a task that unblocks Claude:
```
Create shared marker in ~/fleet/signals/<project>.md:
"Task omnidesk-metrics COMPLETE — unblocks PixelSports-HUD-display"
```

**Shared learning:** Common gotchas go in ~/docs/research/AGENT_LESSONS.md

---

## ✅ Verification Checklist (Before finishing task)

- [ ] Task accepted criteria all checked off
- [ ] Tests pass (npm test)
- [ ] Smoke test passes (npm run verify)
- [ ] Code style matches surrounding code
- [ ] No stray console.log or debug code
- [ ] Commit message is clear and includes why
- [ ] Branch is pushed to origin
- [ ] KANBAN.md updated to DONE
- [ ] Heartbeat updated with completion time
- [ ] Token budget logged

---

## 🚀 Quick Start (Copy-Paste)

For any new project, create `.agent-config.json`:
```json
{
  "worklog_path": "~/omnitender-worklog",
  "kanban_file": "KANBAN.md",
  "target_repos": ["omnidesk", "omniverse", "omnitender-web"],
  "budget_per_task": 50000,
  "escalation_threshold": 50000,
  "max_test_retries": 2,
  "heartbeat_file": "~/fleet/status/<project>.md"
}
```

Then run:
```bash
export AGENT_CONFIG=~/.agent-config.json
# Agent reads this and knows where to find everything
```

---

## 📞 Escalation Checklist

Escalate to you (user) when:
- [ ] Token budget exhausted
- [ ] > 2 consecutive test failures
- [ ] Design decision unclear (need your input)
- [ ] 3+ tasks blocked (cascade)
- [ ] Merge conflict with upstream
- [ ] Security/compliance question
- [ ] Performance regression detected

**How to escalate:**
1. Create ~/fleet/questions.md entry
2. Update KANBAN.md: "Blocker: [reason] — needs user input"
3. Update heartbeat: "⚠️ Escalated to user — waiting for decision"
4. Do NOT spin; pick a different task if one is available

---

## 🎯 Success Metrics

Agent is working well if:
- ✅ Heartbeat updates every 5–10 minutes (shows liveness)
- ✅ Tasks move from TO DO → WORKING → DONE on schedule
- ✅ Tests pass on first run (or second if sequential)
- ✅ Token budget used efficiently (~40k per non-trivial task)
- ✅ No stale WIP branches (everything gets pushed)
- ✅ Context preserved (can resume mid-project)

---

## 🔄 Handoff & Resume

If agent stops mid-task:
1. All work is committed (checked in Phase 2)
2. KANBAN.md shows task status (WORKING/BLOCKED/DONE)
3. Heartbeat shows last activity timestamp
4. Branch exists with WIP code: `work/<task-name>`

To resume:
1. Agent reads KANBAN.md, sees WORKING task
2. Agent checks git: any uncommitted changes?
3. Agent either:
   - Completes the task and moves to DONE, or
   - Moves to BLOCKED if stuck, documents reason
4. Picks next available task

**All state is in git.** No in-memory state lost.

---

**This is the unified system for Claude + Gemini.** Copy-paste this into any project and both agents can work reliably. 🚀

