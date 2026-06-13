# Vertex AI + GCP Credits — CodeMonkeys hook

**Project:** `codemonkeys-498819` · **Region:** `us-central1`  
**Goal:** Spend GCP billing credits on Vertex Gemini instead of AI Studio keys or Cursor credits.

---

## Portable setup (Linux + Windows + every Cursor machine)

**Canonical kit:** `projects/shared/vertex-credits/` (in git — travels with repos)

| OS | Run once on that machine |
|----|--------------------------|
| Linux / macOS / WSL | `bash projects/shared/vertex-credits/setup.sh` |
| Windows | `powershell -ExecutionPolicy Bypass -File projects\shared\vertex-credits\setup.ps1` |

Verify anywhere:

```bash
python projects/shared/vertex-credits/verify_vertex.py
```

**Per-machine config** (not in git):

| OS | Path |
|----|------|
| Linux | `~/.config/codemonkeys/vertex.env` |
| Windows | `%APPDATA%\codemonkeys\vertex.env` |

Optional service account (best for matching behavior across PCs): save JSON as `vertex-sa.json` in the same folder.

Setup installs Cursor rule → `~/.cursor/rules/vertex-gcp-credits.mdc` so agents prefer Vertex for batch work.

See **`projects/shared/vertex-credits/README.md`** for full cross-platform guide.

---

## This Linux machine

You have Application Default Credentials:

```text
~/.config/gcloud/application_default_credentials.json
quota_project: codemonkeys-498819
```

Vertex test succeeded with `google/gemini-2.5-flash`. **No API key paste required for local dev.**

---

## CodeMonkeys (agent console)

New provider **`vertex-gemini`** in ⚙ Models:

- Kind: `vertex` (OAuth via ADC or service account JSON)
- Models: `google/gemini-2.5-flash`, `google/gemini-2.5-pro`, …
- **Auto + free fallback priority** — burns GCP credits before AI Studio / OpenRouter
- Session budget tracks `$0` for Vertex (credits are separate bucket)

Local run:

```bash
cd ~/projects/claude/CodeMonkeys
GOOGLE_CLOUD_PROJECT=codemonkeys-498819 \
  .venv/bin/python -m pip install google-auth
DATA_DIR=./data .venv/bin/uvicorn server:app --port 8080
```

In UI: select **auto** or **vertex-gemini** — fleet subagents use credits.

---

## Batch burn script (games + revenue)

Frivolous-but-productive content generation:

```bash
cd ~/projects/claude/CodeMonkeys
.venv/bin/python scripts/vertex_burn.py --list
.venv/bin/python scripts/vertex_burn.py --all
.venv/bin/python scripts/vertex_burn.py --job freak-franchise-expand --model google/gemini-2.5-pro
```

Output: `~/projects/claude/PixelSports/docs/vertex-generated/`

Jobs cover: Freak Franchise expansion, itch copy, payment playbook, PixelSports marketing, DrivingMeNuts events, Meniscus microcopy, OmniTender absurd bids.

---

## Fly.io / production CodeMonkeys

ADC from your laptop does **not** transfer to Fly. Create a service account:

1. [GCP Console → IAM → Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts?project=codemonkeys-498819)
2. Create `codemonkeys-vertex` → role **Vertex AI User**
3. JSON key → Fly secret (never commit):

```bash
fly secrets set \
  GOOGLE_CLOUD_PROJECT=codemonkeys-498819 \
  GOOGLE_CLOUD_REGION=us-central1 \
  VERTEX_CREDENTIALS_JSON='{"type":"service_account",...}'
```

---

## Billing hygiene

1. [Billing → Credits](https://console.cloud.google.com/billing) — note **expiry**
2. Budget alerts at $100 / $500 / $1200
3. Enable only: **Vertex AI API**

---

## What this does NOT do

- Does not replace **Cursor** interactive coding (keep Cursor for IDE)
- Does not auto-charge AI Studio keys
- Does not connect to Cursor cloud directly — hook is **CodeMonkeys + vertex_burn.py** on your machine/Fly

---

*Institute in situ · spend credits on goodness.*
