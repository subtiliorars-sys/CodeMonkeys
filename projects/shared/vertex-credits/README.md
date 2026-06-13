# Vertex GCP credits — portable kit

Spend **`codemonkeys-498819`** billing credits on Vertex Gemini from **any machine** where you use Cursor + the same git repos.

## Quick start

| OS | One-time setup |
|----|----------------|
| **Linux / macOS / WSL** | `bash projects/shared/vertex-credits/setup.sh` |
| **Windows** | `powershell -ExecutionPolicy Bypass -File projects\shared\vertex-credits\setup.ps1` |

Then verify:

```bash
python projects/shared/vertex-credits/verify_vertex.py
```

## What syncs vs what doesn't

| Syncs via git (all machines) | Per-machine (run setup once each) |
|------------------------------|-----------------------------------|
| CodeMonkeys `vertex-gemini` provider | `~/.config/codemonkeys/vertex.env` |
| `vertex_burn.py` + job manifest | `%APPDATA%\codemonkeys\vertex.env` |
| Cursor rule template in this folder | gcloud ADC **or** `vertex-sa.json` |
| Generated content in `PixelSports/docs/vertex-generated/` | `pip install google-auth` in venv |

**Cursor accounts:** Cursor does not sync GCP auth. Pull the same repos on Windows/Linux, run **setup once per machine**, and you get the same behavior.

**Cursor billing:** Interactive Cursor Agent still uses Cursor credits. GCP credits burn via **CodeMonkeys subagents** and **`vertex_burn.py`** only.

## Auth options (pick one per machine)

### A. Service account JSON (most portable — same file everywhere)

1. [GCP Console → Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts?project=codemonkeys-498819) → create `codemonkeys-vertex` → **Vertex AI User**
2. Download JSON key **once**
3. Copy to:
   - Linux: `~/.config/codemonkeys/vertex-sa.json`
   - Windows: `%APPDATA%\codemonkeys\vertex-sa.json`
4. Or: `VERTEX_SA_SRC=/path/to/key.json bash setup.sh`

Store the JSON in your password manager — **never commit to git**.

### B. gcloud login (easiest per machine)

Install [Google Cloud SDK](https://cloud.google.com/sdk/docs/install), then setup script runs:

```bash
gcloud auth application-default login --project=codemonkeys-498819
```

Same Google account on Windows/Linux = same project access; credentials file path differs by OS (handled automatically).

## Config file (`vertex.env`)

Non-secret defaults (setup scripts create this):

```env
GOOGLE_CLOUD_PROJECT=codemonkeys-498819
GOOGLE_CLOUD_REGION=us-central1
# GOOGLE_APPLICATION_CREDENTIALS=...  # if using service account file
```

CodeMonkeys and `vertex_burn.py` load this automatically.

## Daily use

```bash
# Burn credits on game + revenue batch jobs
cd projects/claude/CodeMonkeys
.venv/bin/python scripts/vertex_burn.py --all

# CodeMonkeys console — auto prefers vertex-gemini when creds present
DATA_DIR=./data .venv/bin/uvicorn server:app --port 8080
```

## Cursor rule

Setup copies `cursor-rule-vertex-gcp-credits.mdc` → `~/.cursor/rules/` so agents on that machine prefer Vertex for volume work.

Re-run setup after cloning on a new PC.

## Fly.io / servers

Set Fly secret `VERTEX_CREDENTIALS_JSON` (full JSON string) — see `CodeMonkeys/docs/VERTEX_GCP_CREDITS.md`.

## Files in this kit

| File | Purpose |
|------|---------|
| `setup.sh` / `setup.ps1` | One-time machine setup |
| `verify_vertex.py` | Test API + auth |
| `vertex_env.py` | Shared env loader |
| `vertex.env.example` | Template |
| `cursor-rule-vertex-gcp-credits.mdc` | Cursor agent instructions |

## Billing

Check [Credits expiry](https://console.cloud.google.com/billing) · budget alerts at $100 / $500 / $1200.
