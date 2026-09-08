# ✈️ MASTER IN-FLIGHT DOCUMENT

This document serves as the master status dashboard and playbook for launching the autonomous agent fleet to work in the background without requiring constant manual approvals.

---

## 📊 FLEET STATUS OVERVIEW

| Project / Repository | Fleet / Owner | Current Branch | PR Status | Next Background Task / Action |
| :--- | :--- | :--- | :--- | :--- |
| **CodeMonkeys** | Claude / Cline | `work/ideation-sweep` | PR #148 Open (Ideation Sweep) | Review session tagging / disk health features |
| **MeniscusMaximus** | Claude / Cline | `work/ideation-sweep` | PR #168 Open (Ideation Sweep) | Merge `work/frontend-polish` (auto-deploys); audit taxonomy |
| **TradeGame** | Claude / Cline | `work/ideation-sweep` | PR #63 Open (Ideation Sweep) | Review XP duplication safeguards and Forex checks |
| **DrivingMeNuts** | Claude / Cline | `work/ideation-sweep` | PR #113 Open (Ideation Sweep) | Verify ledger weather logs and supplier readout |
| **PixelSports** | Claude / Cline | `work/ideation-sweep` | PR #53 Open (Ideation Sweep) | Validate particle effects/pop animations |
| **omnitender-web** | Gemini | `work/dashboard` | PR #7 Pending Push | Push `work/frontend-polish` or merge dashboard polish |
| **omniverse** | Gemini | `work/omniverse-email-fallback-monitor` | PR #21 Open (Email Fallback Monitor) | Monitor queue retry logs |
| **omnidesk** | Gemini | `work/phase2-polish2` | Main merged | Run UX/metrics polishing |
| **omni-herald** | Gemini | `work/deploy-note` | Blocked | Awaiting Gemini API Key setting |
| **agent-system** | Shared | `work/resilience-timers` | PR #13 pending | Deploy cockpit-writes W1 (billing validation needed) |
| **Ilerioluwa** | Shared | `work/ideation-sweep` | PR #8 Open (Preview Ideation Sweep) | Review stopwatch timer widget & WhatsApp templates |

---

## 🚀 HOW TO LAUNCH THE FLEET CONTINUOUSLY

To run agents continuously in the background without needing step-by-step approvals:

### Option 1: Use the `/goal` Slash Command
If you want to set me (or other agents) off on a long-running task and let it run until it is complete, recommend using the `/goal` command:
> **User Prompt Example:**
> `/goal Resume frontend polish wave from ~/fleet/RELAUNCH_PROMPTS.md and open PRs for all incomplete projects.`

### Option 2: Use the `/teamwork-preview` Slash Command
If you want to spin up a team of autonomous agents working together on multiple repositories in parallel:
> **User Prompt Example:**
> `/teamwork-preview Launch the agent fleet on CodeMonkeys, TradeGame, and DrivingMeNuts to run autonomous 12-to-4 ideation sweeps concurrently.`

### Option 3: Run the Local Autonomous Loops
Each project has a background protocol configured in `~/projects/shared/fleet/status/`. You can instruct us to:
1. Initialize/run autonomous 12-to-4 ideation sweeps.
2. Resolve the minor non-blocking tasks listed in the `## Next / safe parallel queue` of their respective status files.

---

## 🛠️ CONTINUOUS TASK BACKLOG (SAFE TO START)

Below are the safe tasks that the fleet can work on continuously in the background without gating on user decisions:

### 1. CodeMonkeys (Claude Territory)
- **Task:** Push local branch `work/frontend-polish` (`cc4d1d4`) and open its PR.
- **Task:** Implement test-coverage expansion for auth-token forgery and users.json atomic writes (safe, read-only tests).
- **Task:** Run the `12-to-4` autonomous ideation sweep.

### 2. TradeGame (Claude Territory)
- **Task:** Run the Drawdown-Survival drill pass implementation.
- **Task:** Update the Preview repository with sanitized docs and tests.

### 3. DrivingMeNuts (Claude Territory)
- **Task:** Implement the scale-corrected upgrade costs (~$1.5k) and push to the accessibility branch.

### 4. OmniTender Family (Gemini Territory)
- **Task:** Complete the dashboard metrics cards with collapsible details on `omnitender-web`.
- **Task:** Verify and push the frontend-polish changes on `omniverse`.
- **Task:** Audit public Preview repos to ensure no confidential data is exposed.

---

## 📞 ESCALATION & BLOCKED TRACKING
- If the fleet encounters a blocker, it will append it to `~/projects/shared/fleet/questions.md` and set its state to `BLOCKED`.
- The fleet will then immediately pick up the next task from the **Safe Parallel Queue** so that progress never stalls.
