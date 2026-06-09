#!/usr/bin/env python3
"""
🍌🌉 OpenRouter Bridge for Banana Shelter
===========================================
Complete integration module for the OpenRouter API.

Provides model listing, automatic cheapest-model selection, budget-aware
LLM requests, and convenience wrappers matching the gemini_integration
interface.

API keys and budget are managed via config_manager.py — stored in
~/.banana_shelter/config.json with restricted permissions.
"""

import json
import sys
import urllib.error
import urllib.request

from config_manager import (
    get_openrouter_active_key,
    load_config,
    record_spend,
    is_budget_exhausted,
    get_budget_info,
    is_session_exhausted,
    get_session_budget_info,
    record_session_spend,
)

# ── Endpoints ──────────────────────────────────────────────────────

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# ── Hardcoded fallback models ──────────────────────────────────────

FALLBACK_MODELS = [
    {
        "id": "google/gemini-2.0-flash-001",
        "name": "Gemini 2.0 Flash",
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
        "context_length": 1000000,
        "pricing_category": "free",
    },
    {
        "id": "meta-llama/llama-3.2-3b-instruct",
        "name": "Llama 3.2 3B",
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
        "context_length": 128000,
        "pricing_category": "free",
    },
    {
        "id": "mistralai/mistral-7b-instruct",
        "name": "Mistral 7B",
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
        "context_length": 32000,
        "pricing_category": "free",
    },
    {
        "id": "cognitivecomputations/dolphin-mixtral-8x7b",
        "name": "Dolphin Mixtral",
        "cost_per_1k_input": 0.0,
        "cost_per_1k_output": 0.0,
        "context_length": 32000,
        "pricing_category": "free",
    },
    {
        "id": "openai/gpt-4o-mini",
        "name": "GPT-4o Mini",
        "cost_per_1k_input": 0.00015,
        "cost_per_1k_output": 0.0006,
        "context_length": 128000,
        "pricing_category": "cheap",
    },
    {
        "id": "anthropic/claude-3-haiku",
        "name": "Claude 3 Haiku",
        "cost_per_1k_input": 0.00025,
        "cost_per_1k_output": 0.00125,
        "context_length": 200000,
        "pricing_category": "cheap",
    },
    {
        "id": "openai/gpt-4o",
        "name": "GPT-4o",
        "cost_per_1k_input": 0.0025,
        "cost_per_1k_output": 0.01,
        "context_length": 128000,
        "pricing_category": "premium",
    },
]

# ── Token estimation ───────────────────────────────────────────────

def _estimate_tokens(text):
    """
    Rough token estimate: ~1 token per 4 characters.
    Used for cost calculation before the actual API call returns usage.
    """
    return max(1, len(text) // 4)


def _estimate_cost(model, input_text, output_text):
    """
    Calculate approximate cost in USD for a given model and texts.
    Uses the per-1k token prices.
    """
    input_tokens = _estimate_tokens(input_text)
    output_tokens = _estimate_tokens(output_text)

    input_cost = (input_tokens / 1000) * model.get("cost_per_1k_input", 0)
    output_cost = (output_tokens / 1000) * model.get("cost_per_1k_output", 0)

    return input_cost + output_cost


# ── Model listing ──────────────────────────────────────────────────

def fetch_available_models():
    """
    Fetch all models from OpenRouter's /api/v1/models endpoint.
    Returns list of dicts with: id, name, cost_per_1k_input, cost_per_1k_output,
    context_length, pricing_category.

    Uses the first active OpenRouter API key.
    Falls back to FALLBACK_MODELS if the API cannot be reached.
    """
    api_key = get_openrouter_active_key()
    if not api_key:
        return list(FALLBACK_MODELS)

    req = urllib.request.Request(
        OPENROUTER_MODELS_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            OSError) as e:
        print(f"  ⚠️ OpenRouter model list fetch failed: {e}", file=sys.stderr)
        return list(FALLBACK_MODELS)

    # OpenRouter returns {"data": [...]}
    raw_models = data.get("data", [])
    if not raw_models:
        return list(FALLBACK_MODELS)

    models = []
    for m in raw_models:
        model_id = m.get("id", "")
        if not model_id:
            continue

        # Extract pricing info — OpenRouter returns pricing as
        # {"prompt": 0.0, "completion": 0.0} per token
        pricing = m.get("pricing", {}) or {}
        cost_in = float(pricing.get("prompt", 0) or 0)
        cost_out = float(pricing.get("completion", 0) or 0)

        # Convert per-token to per-1k-tokens for consistency
        cost_per_1k_in = cost_in * 1000
        cost_per_1k_out = cost_out * 1000

        # Context length from the API
        context = m.get("context_length", 0) or 0

        # Determine pricing category
        if cost_per_1k_in == 0 and cost_per_1k_out == 0:
            category = "free"
        elif cost_per_1k_in <= 0.001 and cost_per_1k_out <= 0.005:
            category = "cheap"
        else:
            category = "premium"

        models.append({
            "id": model_id,
            "name": m.get("name", model_id),
            "cost_per_1k_input": cost_per_1k_in,
            "cost_per_1k_output": cost_per_1k_out,
            "context_length": context,
            "pricing_category": category,
        })

    # If API returned no usable models, fall back
    if not models:
        return list(FALLBACK_MODELS)

    return models


# ── Cheapest model selection ───────────────────────────────────────

def select_cheapest_model(task_type="general", available_models=None, budget_exhausted=False):
    """
    Select the cheapest model appropriate for the task.

    Task types:
      "general"  — any model works (sorted by cost ascending)
      "creative" — needs higher temperature models (prefer non-free with
                   lower output cost among cheap models)
      "code"     — prefers models known for code performance
                   (prioritise free code-capable models first)
      "fast"     — needs low latency (small/light models first)

    Sorts by cost_per_1k_input ascending.
    Free models (cost=0) always selected first.
    Within the same cost tier, prefers models with larger context_length
    (more capable).

    When budget_exhausted=True, ONLY free models (cost=0) are returned.
    """
    if available_models is None:
        available_models = fetch_available_models()

    if not available_models:
        return None

    # Separate free and paid
    free = [m for m in available_models if m.get("cost_per_1k_input", 0) == 0.0]
    paid = [m for m in available_models if m.get("cost_per_1k_input", 0) > 0.0]

    # Sort free models: prefer larger context (more capable)
    free.sort(key=lambda m: -m.get("context_length", 0))

    # Sort paid models: by input cost asc, then by output cost asc,
    # then by context_length desc (more capable for same price)
    paid.sort(key=lambda m: (
        m.get("cost_per_1k_input", 0),
        m.get("cost_per_1k_output", 0),
        -m.get("context_length", 0),
    ))

    # ── Budget exhausted mode: free models ONLY ─────────────────
    if budget_exhausted:
        if free:
            if task_type == "fast":
                # Fast → smallest model
                free_sorted = sorted(free, key=lambda m: m.get("context_length", 0))
            elif task_type == "code":
                # Code → prefer known code-capable free models
                code_free_ids = [
                    "meta-llama/llama-3.2-3b-instruct",
                    "google/gemini-2.0-flash-001",
                    "cognitivecomputations/dolphin-mixtral-8x7b",
                    "mistralai/mistral-7b-instruct",
                ]
                for mid in code_free_ids:
                    for m in free:
                        if m["id"] == mid:
                            return m
                free_sorted = free  # already sorted by largest context
            else:
                free_sorted = free
            return free_sorted[0]
        return None  # No free models available at all

    # ── Normal mode (budget OK) ─────────────────────────────────

    if task_type == "fast":
        # For fast tasks, prefer smallest free model (short context = small model)
        if free:
            free.sort(key=lambda m: m.get("context_length", 0))
            return free[0]
        # Fall through to cheapest paid
        if paid:
            return paid[0]
        return None

    if task_type == "creative":
        # Creative tasks: prefer cheap paid models (free models sometimes
        # lack nuance). Pick cheapest paid that isn't free.
        # Among same price, prefer larger context for better coherence.
        if paid:
            return paid[0]
        if free:
            return free[0]
        return None

    if task_type == "code":
        # Code tasks: prefer free code-capable models FIRST,
        # then cheapest paid option.
        code_friendly_ids = [
            "google/gemini-2.0-flash-001",
            "meta-llama/llama-3.2-3b-instruct",
            "cognitivecomputations/dolphin-mixtral-8x7b",
            "mistralai/mistral-7b-instruct",
            "openai/gpt-4o-mini",
            "anthropic/claude-3-haiku",
        ]
        for model_id in code_friendly_ids:
            for m in available_models:
                if m["id"] == model_id:
                    return m
        # Fall through: best free model (largest context)
        if free:
            return free[0]
        if paid:
            return paid[0]
        return None

    # "general" — default: free first (most capable free = largest context),
    # then cheapest paid
    if free:
        return free[0]
    if paid:
        return paid[0]
    return None


# ── Budget checking ────────────────────────────────────────────────

def check_budget():
    """
    Check if we have budget remaining. Returns dict with:
    within_budget, budget_limit, budget_spent, remaining, exhausted
    """
    info = get_budget_info()
    exhausted = is_budget_exhausted()
    return {
        "within_budget": not exhausted,
        "budget_limit": info["limit"],
        "budget_spent": info["spent"],
        "remaining": info["remaining"],
        "exhausted": exhausted,
    }


# ── OpenRouter API call ────────────────────────────────────────────

def _make_openrouter_request(
    prompt,
    system_instruction=None,
    temperature=0.8,
    max_tokens=200,
    model=None,
    api_key_override=None,
    skip_budget_check=False,
):
    """
    Make a request to OpenRouter /api/v1/chat/completions.

    If model is None, uses select_cheapest_model() to pick one.
    Records spend via config_manager.record_spend().
    Returns response text or None on failure.

    Args:
        api_key_override: Use this key instead of the system key.
            Used when a user provides their own BYOK for Change Forge.
        skip_budget_check: Skip the system budget check.
            Used when the caller handles their own budget (per-user BYOK).
    """
    # Check system budget — skip if caller handles it (e.g., per-user)
    if not skip_budget_check:
        budget_exhausted = is_budget_exhausted()
        session_exhausted = is_session_exhausted()
        any_exhausted = budget_exhausted or session_exhausted
        if any_exhausted:
            budget = get_budget_info()
            session = get_session_budget_info()
            print(
                f"\n  ⚠️⚠️⚠️  BUDGET EXHAUSTED  ⚠️⚠️⚠️\n"
                f"  Monthly: ${budget['spent']:.2f} / ${budget['limit']:.2f}\n"
                f"  Session: ${session['spent']:.2f} / ${session['limit']:.2f}\n"
                f"  → Switching to FREE MODELS ONLY (cost=$0)\n"
                f"  → Set a higher budget with /budget set <amount> or /budget session <amount>\n",
                file=sys.stderr,
            )

    # Use override key if provided, otherwise system key
    if api_key_override:
        api_key = api_key_override
    else:
        api_key = get_openrouter_active_key()

    if not api_key:
        print("  ⚠️ No OpenRouter API key configured.", file=sys.stderr)
        return None

    # Pick model if not specified
    budget_exhausted_flag = False if skip_budget_check else (
        is_budget_exhausted() or is_session_exhausted()
    )
    if model is None:
        task_type = _infer_task_type(prompt)
        model = select_cheapest_model(task_type=task_type, budget_exhausted=budget_exhausted_flag)
    elif isinstance(model, str):
        # If model is a string id, look it up in available models
        models = fetch_available_models()
        model_obj = next((m for m in models if m["id"] == model), None)
        if model_obj is None:
            # If not found, create a minimal stub for cost estimation
            model_obj = {
                "id": model,
                "name": model,
                "cost_per_1k_input": 0.0,
                "cost_per_1k_output": 0.0,
                "context_length": 0,
                "pricing_category": "unknown",
            }
        model = model_obj

    if model is None:
        print("  ⚠️ No suitable model found.", file=sys.stderr)
        return None

    model_id = model["id"] if isinstance(model, dict) else model

    # Build messages
    messages = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    # Build payload
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_CHAT_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  ⚠️ OpenRouter API error ({e.code}): {body}", file=sys.stderr)
        return None
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        print(f"  ⚠️ OpenRouter request failed: {e}", file=sys.stderr)
        return None

    # Extract response text (OpenRouter uses OpenAI format)
    choices = result.get("choices", [])
    if not choices:
        return None

    response_text = choices[0].get("message", {}).get("content", "")
    if not response_text:
        return None

    # Record spend — free model usage doesn't count toward budget
    usage = result.get("usage", {})
    if usage:
        # OpenRouter sometimes returns usage with prompt_tokens and
        # completion_tokens
        input_tokens = usage.get("prompt_tokens", 0) or 0
        output_tokens = usage.get("completion_tokens", 0) or 0
        input_cost = (input_tokens / 1000) * model.get("cost_per_1k_input", 0)
        output_cost = (output_tokens / 1000) * model.get("cost_per_1k_output", 0)
        total_cost = input_cost + output_cost
    else:
        # Estimate based on text length
        total_cost = _estimate_cost(model, prompt, response_text)

    # Free models never add to budget — only count paid spend
    if model.get("cost_per_1k_input", 0) == 0.0 and model.get("cost_per_1k_output", 0) == 0.0:
        total_cost = 0.0
    elif total_cost <= 0:
        # Minimum charge for a non-free model: ~100 tokens of input
        total_cost = (100 / 1000) * model.get("cost_per_1k_input", 0.0001)
        if total_cost <= 0:
            total_cost = 0.00001  # Absolute minimum

    if total_cost > 0.0:
        record_spend(total_cost)
        if not skip_budget_check:
            record_session_spend(total_cost)

    return response_text.strip()


def _infer_task_type(prompt):
    """
    Infer the task type from the prompt text.
    Returns one of "general", "creative", "code", or "fast".
    """
    prompt_lower = prompt.lower()

    # Code detection
    code_indicators = [
        "def ", "class ", "import ", "function", "return ",
        "```python", "```javascript", "// ", "#include", "public class",
    ]
    if any(indicator in prompt for indicator in code_indicators):
        return "code"

    # Creative detection
    creative_indicators = [
        "story", "poem", "write a", "describe", "narrative",
        "creative", "imagine", "generate", "tale",
    ]
    if any(word in prompt_lower for word in creative_indicators):
        return "creative"

    # Fast detection — short prompts likely need quick responses
    if len(prompt) < 100:
        return "fast"

    return "general"


# ── Convenience wrappers ───────────────────────────────────────────

def is_openrouter_available():
    """
    Check if OpenRouter key is configured.
    Returns True if at least one active OpenRouter key exists.
    """
    return bool(get_openrouter_active_key())


def test_openrouter_connection():
    """
    Test connection to OpenRouter API.
    Returns (success: bool, message: str)
    """
    api_key = get_openrouter_active_key()
    if not api_key:
        return False, "No OpenRouter API key configured. Run: python3 config_manager.py"

    # Try a minimal chat request
    response = _make_openrouter_request(
        prompt="Say exactly: OK",
        system_instruction=None,
        temperature=0.1,
        max_tokens=10,
    )

    if response and "OK" in response:
        return True, "✅ OpenRouter API connection successful!"
    elif response:
        return True, f"✅ Connected! (Got: {response[:50]})"
    else:
        return False, "❌ Could not reach OpenRouter API. Check your key and internet."


# ── Entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  🧪 OpenRouter Bridge Test\n")

    print("  🔑 Checking availability...")
    avail = is_openrouter_available()
    print(f"     {'✅ Key configured' if avail else '❌ No key configured'}")

    if avail:
        print("\n  📋 Fetching available models...")
        models = fetch_available_models()
        print(f"     Found {len(models)} models")
        if models:
            print(f"     First few:")
            for m in models[:5]:
                cat_icon = "🆓" if m["pricing_category"] == "free" else "💰"
                print(f"       {cat_icon} {m['id']} — ${m['cost_per_1k_input']:.6f}/1k in")

        print("\n  🤖 Testing connection...")
        success, msg = test_openrouter_connection()
        print(f"     {msg}")

        print("\n  💰 Budget status:")
        budget = check_budget()
        print(f"     Spent: ${budget['budget_spent']:.4f} / ${budget['budget_limit']:.2f}")
        print(f"     Remaining: ${budget['remaining']:.4f}")
        print(f"     {'✅ Within budget' if budget['within_budget'] else '💰 Exhausted'}")

        print("\n  🎯 Model selection test:")
        for task in ("general", "code", "creative", "fast"):
            m = select_cheapest_model(task_type=task)
            if m:
                print(f"     {task:10s} → {m['id']} (${m['cost_per_1k_input']:.6f}/1k in)")
