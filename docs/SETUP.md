# CodeMonkeys — Setup (zero to coding, step by step)

Written so a fresh person on a Chromebook can deploy from nothing. Commands run
in the Crostini Linux terminal unless noted.

## 0. Prerequisites (one time)

```bash
# flyctl (Fly.io CLI)
curl -L https://fly.io/install.sh | sh
# add to PATH if the installer tells you to, then:
fly auth login        # opens a browser to log in

# gh (GitHub CLI) — usually already installed; if not:
sudo apt install gh
gh auth login
```

## 1. Create the GitHub token the agents will use

The agents clone and push your repos with a token. Make a **fine-grained PAT**:

1. github.com → Settings → Developer settings → Fine-grained tokens → *Generate new token*
2. Repository access: **Only select repositories** → pick the repos the agents may touch
3. Permissions → Repository → **Contents: Read and write**
4. Copy the token (starts `github_pat_…`). You'll paste it in step 3.

## 2. Launch the Fly app (no deploy yet)

```bash
cd ~/CodeMonkeys
fly launch --copy-config --no-deploy
# - say YES to "copy existing fly.toml"
# - pick an app name (e.g. codemonkeys-<yourword>) and region
fly volumes create cm_data --size 3          # persistent /data disk
```

## 3. Secrets

```bash
fly secrets set GITHUB_TOKEN=github_pat_XXXX
# optional: raise the per-session spend ceiling (default $1.00)
fly secrets set SESSION_BUDGET_USD=2.00
```

Model API keys do **NOT** go in Fly secrets — you paste them later in the UI
(⚙ Models & keys); they're stored on the /data volume.

## 4. Deploy

```bash
fly deploy
fly open        # opens https://<app>.fly.dev
```

## 5. First login (do this immediately)

1. Click **Register the Owner account** → choose username + PIN (6+ chars).
2. A QR code appears. **Scan it into Google Authenticator / Aegis / 1Password
   NOW.** You cannot log in without it. (Locked out anyway? See Troubleshooting.)
3. Click *I've scanned it — enter console*.

The first account becomes **Owner**; registration closes automatically after it.

## 6. Add a model key (pick one or more)

Open **⚙ Models & keys**. Presets exist for all of these — click *edit*, paste
the key, *Save provider*, then ★ to make one the main model.

| Provider | Get a key | Cost |
|---|---|---|
| **Gemini** (`gemini-flash`) | aistudio.google.com → *Get API key* | Free tier ~1,500 req/day on Flash |
| **OpenRouter** (`openrouter-free`) | openrouter.ai → Keys | $0 models (Qwen3 Coder etc.), no card needed |
| **Anthropic** (`claude-sonnet`/`claude-opus`) | console.anthropic.com | paid |

Recommended: `gemini-flash` as main (★), `openrouter-free` enabled as t0,
Claude Sonnet/Opus enabled if you have credits (subagent tiers will use them
only where doctrine demands).

## 7. Clone a repo and code

1. Sidebar → Repos → paste `https://github.com/you/yourrepo` → **clone**
2. Type what you want built (or hit 🎤 and say it). Enter to send.
3. Watch the agents work. When the agent wants to `git push` you'll get a gold
   **APPROVAL REQUIRED** card — read the command, click APPROVE or DENY.

## Local development

```bash
cd ~/CodeMonkeys
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
DATA_DIR=./data ./.venv/bin/uvicorn server:app --reload --port 8080
# browse http://localhost:8080
```

## Troubleshooting

- **Locked out (lost authenticator):**
  `fly ssh console -a <app>` then
  `python /app/scripts/reset_access.py reset-mfa <username>` — it prints a new
  otpauth URI; turn it into a QR at any QR generator or enter the secret manually.
- **"No enabled model provider":** open ⚙ Models & keys, make sure at least one
  provider has a key AND is enabled, and ★ a main model.
- **Budget halt:** sessions stop at `SESSION_BUDGET_USD` (default $1). Raise the
  secret and `fly deploy`, or start a new session.
- **App asleep:** `min_machines_running = 0` means first request takes a few
  seconds to wake the machine. That's the cheap setting working as intended.
- **Logs:** `fly logs -a <app>`.
