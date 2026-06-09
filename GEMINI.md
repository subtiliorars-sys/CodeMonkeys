# Gemini Documentation — CodeMonkeys

This file notates the architectural and feature changes implemented during the Strategic Improvements Campaign (June 2026).

## New Features

### 1. GitHub Pull Request Bridge
- **Backend**: `/api/github/pr` (POST) — Creates a PR on GitHub. Uses `GITHUB_TOKEN_VAL` and repo config from `MODELS_FILE`.
- **Frontend**: "🚀 Submit Pull Request" button in the Repos sidebar. Prompts the session model for an AI summary before creation.

### 2. Agent Corps Persona Editor
- **Backend**: 
  - `/api/corps/list` (GET) — Lists `.md` files in `corps/agents/`.
  - `/api/corps/read/{name}` (GET) — Reads a persona file.
  - `/api/corps/write` (POST) — Saves a persona file with traversal guards.
- **Frontend**: "⚙ Agent Corps (Personas)" in Settings. Opens a modal editor for subagent definitions.

### 3. Anonymous Feedback System (Ported from MM)
- **Backend**: `/api/feedback` (Intake), `/api/feedback/list` (Admin), `/api/feedback/status` (Triage), `/api/feedback/shot/{name}` (Secure serving).
- **Frontend**:
  - Floating 💬 button with **Visual Annotations** (Redact/Highlight).
  - "📥 Feedback Inbox" in Settings (Owner-only).

### 4. Unified Omni-Search
- **Shortcut**: `Ctrl+K`
- **Scope**: Fuzzy search over Tabs, Settings, and Active Sessions.
- **File**: `static/forge/omni-search.js`

## Technical Notes
- **Dependencies**: Added `vendor-html2canvas.min.js` for client-side capture.
- **Security**: All management endpoints use `verify_owner`. Feedback intake uses `verify_user` + rate limiting.
