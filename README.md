# 🍌 CodeMonkeys — Banana Shelter & Cline Proxy

A local AI toolshed: Banana Shelter game + Cline API Proxy for VS Code.

## 🌉 Cline Proxy — Local API for VS Code AI

Run a local OpenAI-compatible proxy server that routes your Cline/CodeBuddy
requests through **OpenRouter** (free models!), **Gemini**, **Anthropic**, or
**Ollama** with automatic fallback and key rotation.

### Quick Start (Linux / "The Momputer")

```bash
# One-command deploy
chmod +x deploy_linux.sh
./deploy_linux.sh

# Or manually:
python3 cline_proxy.py
```

The server starts on **`http://0.0.0.0:4891/v1`**.

### Configure Cline in VS Code

Add to your VS Code `settings.json`:

```json
{
  "cline.apiProvider": "openai",
  "cline.openAiApiUrl": "http://localhost:4891/v1",
  "cline.openAiModel": "free",
  "cline.openAiKey": "proxy-local"
}
```

Or use these built-in model aliases:

| Alias      | Model                                                                | Cost  |
|------------|----------------------------------------------------------------------|-------|
| `free`     | Google Gemini 2.0 Flash (via OpenRouter)                              | $0    |
| `fast`     | Meta Llama 3.2 3B Instruct (via OpenRouter)                           | $0    |
| `cheap`    | Google Gemini 2.0 Flash-001 (via OpenRouter)                          | $0    |
| `balanced` | Mistral 7B Instruct (via OpenRouter)                                  | $0    |
| `code`     | Google Gemini 2.0 Flash-001 (via OpenRouter)                          | $0    |
| `smart`    | GPT-4o Mini (via OpenRouter)                                          | ~$0.0003/call |
| `fast-gemini` | Gemini 2.0 Flash (direct via Google API key)                      | Free tier |

### 🌟 Free Models (No API Key Needed? Almost!)

Most aliases route through **OpenRouter** which offers many **totally free** models:
- `google/gemini-2.0-flash-001` — Gemini Flash, 1M context, $0
- `meta-llama/llama-3.2-3b-instruct` — Tiny Llama, fast responses, $0
- `mistralai/mistral-7b-instruct` — Mistral 7B, solid all-rounder, $0

To use these, you need an **OpenRouter API key** (it's free — just sign up):
1. Go to https://openrouter.ai/keys
2. Create a free account & API key
3. Add it: `python3 config_manager.py`

Even with a key, **free models cost you $0**. The key is just for rate limiting.

### Budget-Aware Routing 💰

The proxy has built-in budget tracking:
- **Monthly budget**: Default $1.00 (configurable)
- **Session budget**: Default $0.50 (resets each session)
- When either is exhausted, the proxy **automatically forces `free` models**
- Set via: `/budget set <amount>` and `/budget session <amount>`

### Model Routing Chain

1. **OpenRouter** — most models, free tier available
2. **Gemini** — direct Google API, free tier
3. **Anthropic** — direct Claude API
4. **Ollama** — local models (requires Ollama running)

```bash
# Test the proxy is running
curl http://localhost:4891/v1/models

# Check status & key health
curl http://localhost:4891/v1/proxy/status

# Quick chat test
curl -X POST http://localhost:4891/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"free","messages":[{"role":"user","content":"Say hello!"}]}'
```

### Manual Linux Deploy

```bash
git clone <this-repo> ~/codemonkeys
cd ~/codemonkeys

# No pip install needed — all stdlib!
python3 cline_proxy.py --port 4891 --verbose

# For local models (optional):
# curl -fsSL https://ollama.com/install.sh | sh
# ollama pull llama3.2:3b
```

### Add API Keys

```bash
python3 config_manager.py
```

Follow the interactive prompts to add OpenRouter, Gemini, or Anthropic keys.

---

## 🎮 Banana Shelter Game

Save 20 coins from evil kayakers!

```bash
python3 banana_shelter.py
```

*Built with 🍌 by the CodeMonkeys*
