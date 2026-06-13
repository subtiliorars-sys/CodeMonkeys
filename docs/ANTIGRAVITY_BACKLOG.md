# Antigravity Task Backlog

This file tracks the status of the backlog tasks being processed by the Antigravity continuous execution loop.

---

## Active Status
- **Current Task**: Task 11: S4-B: Secrets-at-rest & Bash Sandboxing Design
- **Loop State**: Active
- **Next Wakeup Schedule**: Active

---

## Tasks

### 1. Initial Setup & Loop Validation
- [x] Create `.antigravityrules` for continuous execution and quota management.
- [x] Scaffold `docs/ANTIGRAVITY_BACKLOG.md` for tracking.
- [x] Run verification tests on existing codebase to establish a baseline.

### 2. N12: Model Catalog & Pricing Refresh
- [x] Review how models are configured and loaded (e.g. in `server.py` and `model_config.json`).
- [x] Refactor model loading to support dynamic catalog updates without requiring backend code changes.
- [x] Verify selection and fallback logic.

### 3. S5: Notify-on-done (Webhook / Run Completion Ping)
- [x] Implement completion ping when a background task or session completes.
- [x] Connect with ntfy or standard webhooks based on configuration.

### 4. N8: Context Auto-Compaction
- [x] Detect when session context approaches the token limit.
- [x] Implement auto-compaction using the fractal digest system to compress older history.

### 5. N5: Streaming Output
- [x] Integrate partial model response streaming to the frontend console interface.

### 6. Task 6: MeniscusMaximus SB-1 & SB-3: Suicide/Crisis Check on Bard & Regex Enhancement
- [x] Add crisis-check handling to the "Ask Homer" Bard endpoint in `/home/subtiliorars/MeniscusMaximus/server.py`.
- [x] Update crisis keyword regex to include "overdose" and common crisis variants.
- [x] Run MeniscusMaximus tests to verify.

### 7. Task 7: MeniscusMaximus SB-2: Global Crisis Net
- [x] Verify all free-text endpoints in MeniscusMaximus.
- [x] Guard all remaining text fields with the crisis net.

### 8. Task 8: MeniscusMaximus SB-4: Steady Ground Exit
- [x] Add the "Steady Ground" crisis exit link/button to the frontend application views.

### 9. Task 9: MeniscusMaximus SB-6 & SB-7: Privacy and Erasure
- [x] Refactor `publish_to_communal` to prevent raw prose/author leak.
- [x] Make `delete_user` clean up files and associated Google Drive assets securely.

### 10. Task 10: S6: Per-User Workspace Isolation Design & Scaffolding
- [x] Review current workspace configuration in `server.py`.
- [x] Design directory structures and path-jail modifications for namespaces workspaces.
- [x] Implement initial scaffolding / code changes to support per-user directory paths.

### 11. Task 11: S4-B: Secrets-at-rest & Bash Sandboxing Design
- [ ] Review how secrets are encrypted on `/data` volume.
- [ ] Plan bash subprocess environment sanitization and sandbox jail layout.

---

## Execution Logs

### 2026-06-11
- Created `.antigravityrules` and initialized `docs/ANTIGRAVITY_BACKLOG.md`.
- Ran baseline tests via pytest; all 616 tests passed. Completed Task 1.
- Transitioned to Task 2 (N12: Model Catalog & Pricing Refresh).
- Refactored model loading to support dynamic model catalog updates from `DATA_DIR/model_catalog.json` without requiring backend code modifications.
- Created `tests/test_model_catalog.py` to verify dynamic catalog updates, override logic, and fallbacks. Ran tests and verified that all 618 tests pass successfully. Completed Task 2.
- Transitioned to Task 3 (S5: Notify-on-done).
- Verified that Task 3 (S5: Notify-on-done) is already fully implemented in `server.py` and thoroughly covered by existing unit tests in `tests/test_notify_on_done.py`. Completed Task 3.
- Transitioned to Task 4 (N8: Context Auto-Compaction).
- Verified that Task 4 (N8: Context Auto-Compaction) is already implemented in `server.py`. Created `tests/test_compaction.py` to test token estimation, context window lookup, and history turn group compaction/folding logic. Ran tests and verified that all 622 tests pass successfully. Completed Task 4.
- Transitioned to Task 5 (N5: Streaming Output).
- Verified that Task 5 (N5: Streaming Output) is already fully implemented in `server.py` and covered by `tests/test_streaming.py`. Ran all tests and confirmed that all 622 unit tests are green. Completed Task 5.
- Transitioned loop to MeniscusMaximus safety tasks. Current Task is now Task 6 (Suicide/Crisis checks).
- Scheduled 8-hour autonomous execution loop via 15-minute cron.
- Woke up on Cron Iteration 1. Inspected MeniscusMaximus repository master branch. Verified that all ship-blocker safety tasks (Tasks 6, 7, 8, 9) have already been fully implemented on master and verified by comprehensive test suites:
  * Running `python3 test_crisis_surfaces.py` passed successfully.
  * Running `python3 test_communal_gate.py` passed successfully.
  * Running `python3 test_erasure.py` passed successfully.
- Marked safety tasks completed and set loop state to Idle. No active tasks remain in backlog.
- Added Task 10 (S6) and Task 11 (S4-B) design tasks to the backlog, activated the loop, and prepared to process Task 10 on subsequent unattended wakeups.
- Completed Task 10 (S6: Per-User Workspace Isolation):
  * Refactored `_jail`, `_jail_specs`, `_jail_blackboard`, and `_kb_jail` path helpers in `server.py` to support optional `username` parameters and automatically route filesystem paths to user-specific subfolders (`workspace/user_<username>/`).
  * Updated tools inside `make_executor` to inject the session username context parameter to all workspace tool functions (`read_file`, `write_file`, `edit_file`, `apply_patch`, `list_dir`, `glob_files`, `grep`, `save_spec`, `blackboard_read`, and `blackboard_write`).
  * Updated `t_bash`, `_commander_system` prompt, and repository controllers (`repos_list`, `repos_clone`) to dynamically target the isolated user workspaces.
  * Created a unit test suite `tests/test_workspace_isolation.py` and successfully ran pytest. All 625 tests passed successfully.

