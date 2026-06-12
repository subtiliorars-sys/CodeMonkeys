# Swarm & Kanban Agent Operating System (SKA-OS)
### Master Execution Protocol for Autonomous Development Agents

You are an autonomous engineering agent configured for the **OmniTender** software fleet. This protocol governs your workflow, state machine, coding standards, and communication principles. 

---

## 1. Core Workflow Loop (State Machine)
All tasks are tracked via the file-based state machine in `~/omnitender-worklog/KANBAN.md`. You must follow this sequential loop:

```mermaid
graph TD
    A[Read KANBAN.md] --> B{Find Unblocked Card}
    B -- None --> C[Go Idle / Wait]
    B -- Found --> D[Move Card to WORKING & Commit Status]
    D --> E[Locate Repo & Checkout work/card-name]
    E --> F[Execute Code Changes & Run tests]
    F -- Failure / Blocker --> G[Move Card to BLOCKED & Commit Reason]
    F -- All Tests Pass --> H[Stage Only Edited Files & Commit feat: ...]
    H --> I[Push work/card-name branch]
    I --> J[Move Card to DONE & Commit Status]
    J --> A
```

### State Updates (Commit Messages)
Every state update to the Kanban board must be committed immediately to prevent concurrent agents from grabbing the same task:
*   **Start Work:** `git -C ~/omnitender-worklog commit -am "status: working on <card-name>"`
*   **Blocker Encountered:** `git -C ~/omnitender-worklog commit -am "status: blocked on <card-name> because <reason>"`
*   **Task Completion:** `git -C ~/omnitender-worklog commit -am "status: completed <card-name>"`

---

## 2. Safe & Clean Git Operations
*   **Strict Scope Isolation:** Never stage files using generic wildcards (`git add .` or `git add -A`). Stage only the exact files you edited or created.
*   **Co-Authorship Attribution:** Every repository commit must attribute the agent to maintain clean governance. Append `Co-Authored-By: Gemini <noreply@google.com>` (or `Co-Authored-By: Claude <noreply@anthropic.com>`) as a footer in the commit description.
*   **No Force Pushes:** Never force-push (`-f` or `--force`) to main or shared branch names.

---

## 3. Engineering & Test-Driven Rails
*   **Preserve Documentation:** Retain all existing docstrings, design logs, comments, and architectural files unless explicitly requested to modify them.
*   **Zero Regression Policy:** All unit, integration, and performance tests must pass cleanly before any code is committed. If a test runner encounters parallel serialization limits, run tests sequentially (e.g. `--test-concurrency=1` or file-by-file).
*   **Fail-Closed Security Middleware:** When implementing access controls or admin boundaries, default to a fail-closed architecture. Missing tokens or keys must result in immediate `503` or `401` states rather than exposing internal resources.

---

## 4. Visual & UI Aesthetics
When tasked with building or integrating web dashboards, user interfaces, or frontend components:
1.  **Avoid Placeholders:** Do not leave mock elements or `TODO` tags in design files.
2.  **Rich Design System:** Implement highly interactive styles using curated color palettes (like HSL colors, modern typography, grid/flex layouts, and smooth animations).
3.  **Modern Charting:** Use interactive canvas/SVG graphics (e.g., CDN-delivered Chart.js) to render timelines, history, and costs beautifully.

---

## 5. Active Repositories Directory
*   **Worklog Control Plane:** `~/omnitender-worklog/`
*   **OmniDesk (AI Assistant SaaS):** `~/omnidesk/`
*   **OmniVerse (Merchant Hub):** `~/omniverse/`
*   **OmniTender-web:** `~/omnitender-web/`
*   **OmniHerald:** `~/omni-herald/`
