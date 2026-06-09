#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────
#  🌉 Deploy Cline Proxy — Linux (momputer-ready) 
#  ────────────────────────────────────────────────────────────
#  One-command setup: installs deps, configures, and runs
#  the Cline API proxy for VS Code on your Linux machine.
#
#  Usage:
#    chmod +x deploy_linux.sh && ./deploy_linux.sh
#
#  What it does:
#    1. Checks for Python 3.10+
#    2. Creates a virtual environment
#    3. Verifies / installs Ollama (optional — for local models)
#    4. Launches the proxy server
#    5. Prints Cline VS Code config instructions
# ────────────────────────────────────────────────────────────

set -e

# ── Colors ─────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}  🌉  Cline Proxy — Linux Deploy${NC}"
echo -e "${BLUE}  ═══════════════════════════════════${NC}"
echo ""

# ── Step 1: Check Python ──────────────────────────────────
echo -e "${YELLOW}[1/5]${NC} Checking Python..."
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" --version 2>&1 | grep -oP '\d+\.\d+')
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ] 2>/dev/null; then
            PYTHON="$cmd"
            echo -e "     ${GREEN}✅${NC} Found $cmd $("$cmd" --version 2>&1)"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "     ${RED}❌${NC} Python 3.10+ required."
    echo "     Install it:"
    echo "       sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    exit 1
fi

# ── Step 2: Create virtual environment ────────────────────
echo -e "${YELLOW}[2/5]${NC} Setting up virtual environment..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    $PYTHON -m venv "$VENV_DIR"
    echo -e "     ${GREEN}✅${NC} Created virtual env at $VENV_DIR"
else
    echo -e "     ${GREEN}✅${NC} Virtual env already exists"
fi

source "$VENV_DIR/bin/activate"

# ── Step 3: Check for dependencies ────────────────────────
echo -e "${YELLOW}[3/5]${NC} Checking dependencies..."
# This proxy uses ONLY standard library — no pip installs needed!
echo -e "     ${GREEN}✅${NC} All dependencies are stdlib (no pip required)"

# ── Step 4: Check / install Ollama (optional) ─────────────
echo -e "${YELLOW}[4/5]${NC} Checking Ollama (optional, for local models)..."
if command -v ollama &>/dev/null; then
    echo -e "     ${GREEN}✅${NC} Ollama found at $(which ollama)"
    if curl -s http://localhost:11434/api/tags &>/dev/null; then
        echo -e "     ${GREEN}✅${NC} Ollama service is running"
    else
        echo -e "     ${YELLOW}⚠${NC}  Ollama installed but not running."
        echo -e "     Start it:  ollama serve"
    fi
else
    echo -e "     ${YELLOW}⚠${NC}  Ollama not found (optional)."
    echo -e "     To install for local models:"
    echo -e "       curl -fsSL https://ollama.com/install.sh | sh"
    echo -e "       ollama pull llama3.2:3b"
fi

# ── Step 5: Setup API keys ────────────────────────────────
echo -e "${YELLOW}[5/5]${NC} Checking API keys..."
CONFIG_DIR="$HOME/.banana_shelter"
CONFIG_FILE="$CONFIG_DIR/config.json"

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"

HAS_KEYS=false
if [ -f "$CONFIG_FILE" ]; then
    KEY_COUNT=$($PYTHON -c "
import json
try:
    c = json.load(open('$CONFIG_FILE'))
    print(len(c.get('openrouter_api_keys', [])) + len(c.get('gemini_api_keys', [])))
except: print(0)
" 2>/dev/null || echo 0)
    [ "$KEY_COUNT" -gt 0 ] && HAS_KEYS=true
fi

if [ "$HAS_KEYS" = true ]; then
    echo -e "     ${GREEN}✅${NC} API keys found in $CONFIG_FILE"
else
    echo -e "     ${YELLOW}⚠${NC}  No API keys configured yet."
    echo ""
    echo -e "     To add an OpenRouter API key (free model access):"
    echo "       1. Get a key from https://openrouter.ai/keys"
    echo "       2. Run:  cd $SCRIPT_DIR && python3 config_manager.py"
    echo ""
    echo -e "     ${BLUE}Free models available via OpenRouter:${NC}"
    echo -e "       • google/gemini-2.0-flash-001  (totally free)"
    echo -e "       • meta-llama/llama-3.2-3b-instruct (free)"
    echo -e "       • mistralai/mistral-7b-instruct (free)"
fi

# ── Launch ────────────────────────────────────────────────
echo ""
echo -e "${GREEN}  🚀  Ready to launch!${NC}"
echo ""

PORT="${1:-4891}"

echo -e "  ${BLUE}Starting server on port $PORT...${NC}"
echo -e "  ${BLUE}Point Cline to: http://localhost:$PORT/v1${NC}"
echo -e "  ${BLUE}Use model: free${NC}"
echo ""

cd "$SCRIPT_DIR"
exec python3 cline_proxy.py --port "$PORT" --host 0.0.0.0
