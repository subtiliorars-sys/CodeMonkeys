# Unified Operating System (UOS) — Multi-Agent Collaboration Framework

**Version:** 2.1 (Production Release)  
**Last Updated:** 2026-06-12  
**Purpose:** Standardized coordination protocol for Claude Code, Gemini, and other autonomous agents across all workspaces.  
**Foundation:** Swarm & Kanban Agent Operating System (SKA-OS) — enhanced with token caching strategies, git-based concurrency locks, and edge-case resilience.

---

## 🎯 1. Core Principles

1.  **Git-Backed State Machine** — All task statuses, design decisions, and claims are checked in.
2.  **Optimistic Concurrency Control** — Git-based atomic claims prevent agents from colliding on the same task.
3.  **Resource & Caching Efficiency** — Optimizes token consumption using model-specific caching heuristics.
4.  **Event-Driven Heartbeats** — Progress updates are logged during transition phases, avoiding token-wasting poll loops.
5.  **Fail-Closed Security & Testing** — Gateways, keys, and security parameters default to closed. Failure is escalated early.

---

## 🔄 2. The Core Execution Loop

### Phase 0: Pre-Flight & Budget Checks
1.  **Check Budget:** Read `~/.agent-budget.json`. If `tokens_remaining` is less than `per_task_budget` (default 80k) or `budget_total` is depleted, halt, log `⏸️ Budget Exhausted` to the status board, and exit.
2.  **Write Pre-Flight Heartbeat:**
    ```bash
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) — Agent started Phase 0. Checking board." >> ~/fleet/status/<project>.md
    ```

### Phase 1: Read & Claim Task (Concurrency Lock)
To prevent two agents from simultaneously working on the same task, agents must perform an optimistic commit-lock:
1.  Navigate to the worklog directory: `cd ~/omnitender-worklog`
2.  Run `git pull --rebase` to fetch the latest state.
3.  Examine `KANBAN.md`. Locate the highest-priority task in the **TO DO** section that has no active `[BLOCKED]` flag.
4.  Move the task from **TO DO** to **WORKING** in `KANBAN.md` and stamp it with your agent signature.
5.  Attempt to commit the claim:
    ```bash
    git add KANBAN.md
    git commit -m "status: claiming <task-slug>"
    ```
6.  **Resolve Claim Collision:**
    - Immediately attempt to push: `git push origin master` (if remote exists).
    - If the push succeeds: Proceed to Phase 2.
    - If the push fails due to upstream updates: Run `git pull --rebase`. If `KANBAN.md` conflicts or your chosen task was claimed by another agent in the upstream commits, **abort your claim**, run `git reset --hard HEAD~1`, and return to step 3.

### Phase 2: Checkout & Setup
1.  Navigate to the target repo: `cd <repo-path>`
2.  Verify the repository is clean (`git status`).
3.  Create/checkout the feature branch:
    ```bash
    git checkout -b work/<task-slug>
    ```
4.  Write claim heartbeat:
    ```bash
    echo "  - Claimed task: <task-slug> (branch: work/<task-slug>)" >> ~/fleet/status/<project>.md
    ```

### Phase 3: Implement & Heartbeat
1.  Verify the requirements in the task card (`cards/<task-slug>.md`).
2.  Write code, preserving documentation, docstrings, and inline comments.
3.  **Event-Driven Heartbeats:** Do not loop sleep cycles to write heartbeats. Instead, append to the progress log *only* when a file is created/modified, or when a major implementation step is complete:
    ```bash
    echo "  - Modified: src/index.js (added route handlers)" >> ~/fleet/status/<project>.md
    ```

### Phase 4: Test & Verify
1.  Execute the test suite (e.g. `npm test` or `go test ./...`).
2.  **Test Failure Protocol:**
    - **First Failure:** Run tests sequentially (e.g. `npm test -- --serial` or `--test-concurrency=1`) to eliminate database lock issues or test-runner race conditions.
    - **Second Failure (Persistent):**
      - Check if the failures are due to flaky tests (see Section 4).
      - If it is a real regression: Move the task to **BLOCKED** in `KANBAN.md`, document the traceback/cause, write a ticket entry in `~/fleet/questions.md`, commit the status update to the worklog, and exit.
3.  **Acceptance Gate:** Check off each criterion in the task card. Do not proceed to commit if any criteria are incomplete.

### Phase 5: Attributed Commit & Push
1.  Check `git status` to ensure no stray debug files or temporary assets are present.
2.  Stage *only* the specific files you authored or modified:
    ```bash
    git add src/index.js src/metrics.js ...
    ```
3.  Commit with explicit co-authorship formatting:
    ```bash
    git commit -m "feat: <summary of changes>
    
    Co-Authored-By: <Agent-Name> <noreply@google.com>" --author="<Agent-Name> <noreply@google.com>"
    ```
4.  Push the branch:
    ```bash
    git push origin work/<task-slug>
    ```

### Phase 6: Mark Complete
1.  Navigate to the worklog: `cd ~/omnitender-worklog`
2.  Move the task card from **WORKING** to **DONE** in `KANBAN.md`.
3.  Commit the completion state:
    ```bash
    git add KANBAN.md
    git commit -m "status: completed <task-slug>"
    git push origin master  # if remote exists
    ```
4.  Write final heartbeat:
    ```bash
    echo "  ✅ Task <task-slug> complete." >> ~/fleet/status/<project>.md
    ```

---

## 🧮 3. Model-Specific Execution Strategies

### A. Gemini Optimization Strategy
*   **Context Caching:** Gemini models leverage massive context windows. To maximize efficiency, request context caching for standard libraries, dependency structures, and root documentation that stays static across task runs.
*   **No Wildcard Imports:** When referencing files, feed Gemini precise code modules rather than reading entire directory trees recursively, which degrades reasoning speed.
*   **Large Context Reviews:** Use Gemini's strength to perform whole-project dependency impact analysis prior to editing core files.

### B. Claude Optimization Strategy
*   **Compact Prompting:** Keep prompt history trimmed. Claude performs exceptionally well with target modular edits and direct replacements.
*   **Tool Calling Density:** Limit tool calling loops. Pack multi-file edits into single structured calls (such as multi-replace tools) to conserve tokens and reduce latency.

---

## 🚨 4. Edge Cases & Recovery Protocols

### ⚠️ Flaky Tests
*   A test is categorized as **flaky** if it fails on parallel execution but consistently passes on sequential execution.
*   **Action:** If a test passes when run in isolation, log a warning: `[FLAKY_WARNING] Test <name> succeeded on retry` to the heartbeat file. Do not block the task. Proceed to commit, but append the warning details to the commit description.

### ⚠️ Merge Conflicts
*   If a rebase or check-out fails due to a merge conflict:
    1.  Do not attempt force-merging or brute-force code removal.
    2.  Run `git merge --abort` or `git rebase --abort` to return the repository to a clean state.
    3.  Move the card to **BLOCKED** in `KANBAN.md`.
    4.  Add a conflict resolution request in `~/fleet/questions.md` containing the conflicting branches and files.

### ⚠️ System Reboot / Process Termination
*   If the agent is terminated mid-task (due to shell timeout, system crash, or reboot):
    - Because state is continuously saved in local Git tracking:
      1.  The next agent boot scans `KANBAN.md` and detects the task marked as `WORKING`.
      2.  The agent runs `git status` in the repository, notes the dirty state or the presence of the `work/<task-slug>` branch, and resumes editing directly from Phase 3.

---

## 📞 5. Escalation Rules

Agents must immediately halt work, log status, and wait for human review when:
1.  **Budget Limits Hit:** Per-task budget is exceeded or total budget is less than 50k tokens.
2.  **Unresolved Blockers:** A blocker cascade occurs where more than 2 tasks are blocked by the same root issue.
3.  **Security Fail-Closed Triggered:** Encryption keys, webhook secrets, or third-party API keys are missing or rejected by the test environment.
4.  **Merge Conflicts:** Upstream integration conflicts cannot be resolved automatically.

---

## 📋 6. Setup Template (5-Min Config)

For any new project, initialize `.agent-config.json` in the workspace root:
```json
{
  "worklog_path": "~/my-project-worklog",
  "kanban_file": "KANBAN.md",
  "target_repos": ["web-client", "api-server"],
  "budget_per_task": 80000,
  "escalation_threshold": 50000,
  "max_test_retries": 2,
  "heartbeat_file": "~/fleet/status/my-project.md"
}
```

---

## 🛠️ 7. Troubleshooting Guide

| Problem | Cause | Fix |
| :--- | :--- | :--- |
| **Git Push Collision** | Another agent claimed the task concurrently | Abort commit, run `git pull --rebase`, and select the next unblocked task. |
| **Budget Warning** | Token limit is near depletion | Commit current code state, set status to `BLOCKED`, and request user budget reload. |
| **Database Lock Error** | Concurrency conflicts in test suites | Configure test runner to run sequentially (`--serial` or concurrency level = 1). |
| **Stale Branch Error** | Remote branch is ahead of local branch | Run `git fetch --all` and rebase your feature branch onto `origin/main` before pushing. |

---

## 🔄 Changes from v2.0
- **Optimistic Concurrency Lock:** Implemented Git rebase/push loops to resolve multi-agent claim race conditions.
- **Event-Driven Heartbeats:** Shifted from time-based heartbeats to state/file transition heartbeats to save tokens.
- **Gemini Context Optimization:** Added rules for Gemini context caching and input pruning.
- **Troubleshooting & Edge Cases:** Created formal paths for flaky tests, system crashes, and merge conflicts.
