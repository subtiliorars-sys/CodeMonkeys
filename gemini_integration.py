#!/usr/bin/env python3
"""
🍌✨ Gemini Integration for Banana Shelter
===========================================
Optional AI-powered enhancements using Google's Gemini API.

Features when enabled:
- AI-generated kayaker names (thematic, funny, dynamic)
- Storytelling for in-game events (scavenging descriptions, battle narration)
- Dynamic item descriptions based on context

API key is managed via config_manager.py — stored in ~/.banana_shelter/config.json
with restricted permissions. No browser password prompts involved.
"""

import json
import os
import random
import sys
import urllib.request
import urllib.error
import urllib.parse

from config_manager import get_api_key, load_config, get_openrouter_active_key

# Gemini API endpoint
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
GEMINI_MODEL = "gemini-2.0-flash"


def _make_gemini_request(prompt, system_instruction=None, temperature=0.8, max_tokens=200, model=None):
    """
    Make a request to Gemini or OpenRouter (based on config provider)
    and return the response text.
    """
    config = load_config()
    provider = config.get("provider", "openrouter")

    # ── OpenRouter path ────────────────────────────────────────────
    if provider == "openrouter":
        or_key = get_openrouter_active_key()
        if not or_key:
            # No OpenRouter key configured — fall through to Gemini
            pass
        else:
            from openrouter_bridge import _make_openrouter_request
            return _make_openrouter_request(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=temperature,
                max_tokens=max_tokens,
                model=model,
            )

    # ── Gemini path (default / fallback) ───────────────────────────
    api_key = get_api_key()
    if not api_key:
        return None

    gemini_model = model if model else config.get("gemini_model", GEMINI_MODEL)
    
    url = f"{GEMINI_API_BASE}/{gemini_model}:generateContent?key={api_key}"
    
    contents = []
    if system_instruction:
        contents.append({
            "role": "user",
            "parts": [{"text": f"[System instruction: {system_instruction}]"}]
        })
        contents.append({
            "role": "model",
            "parts": [{"text": "Understood. I will follow those instructions."}]
        })
    
    contents.append({
        "role": "user",
        "parts": [{"text": prompt}]
    })
    
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "topP": 0.95,
        }
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        
        candidates = result.get("candidates", [])
        if candidates:
            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return text.strip()
        return None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"  ⚠️ Gemini API error ({e.code}): {body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  ⚠️ Gemini request failed: {e}", file=sys.stderr)
        return None


def generate_kayaker_name(day):
    """
    Generate a kayaker name using AI based on the current day.
    Falls back to the static name list if API fails or not configured.
    """
    config = load_config()
    if not config.get("ai_kayaker_names"):
        return None  # Feature disabled
    
    prompt = (
        f"Generate ONE ridiculous, thematic evil kayaker name for day {day} "
        f"of a banana shelter defense game. "
        f"Make it funny, water/paddle themed, and slightly threatening. "
        f"Return JUST the name, nothing else. "
        f"Examples: 'The Paddling Menace', 'Captain Splash', 'Smooth-Criminal Steve'"
    )
    
    result = _make_gemini_request(prompt, temperature=0.9)
    if result:
        # Clean up — remove quotes if AI wrapped the name
        result = result.strip('"\' \n')
        return result
    return None


def generate_scavenge_description():
    """
    Generate a vivid description of the morning scavenge.
    Falls back to default if API fails.
    """
    config = load_config()
    if not config.get("ai_storytelling"):
        return None
    
    prompt = (
        "Describe a peaceful morning by a river in 1-2 sentences. "
        "Make it vivid, sensory, and slightly quirky. "
        "Include a banana or banana-adjacent detail. "
        "Keep it under 100 characters."
    )
    
    return _make_gemini_request(prompt, temperature=0.7)


def generate_battle_narration(kayaker_name, attack_type, day):
    """
    Generate dynamic battle narration.
    attack_type: 'punch', 'item', or 'retaliate'
    """
    config = load_config()
    if not config.get("ai_storytelling"):
        return None
    
    if attack_type == "punch":
        prompt = (
            f"Write one punchy (pun intended) combat line about "
            f"punching {kayaker_name} the evil kayaker on day {day} "
            f"of a banana shelter defense game. Exclamation! Under 80 chars."
        )
    elif attack_type == "retaliate":
        prompt = (
            f"Write one line about {kayaker_name} the evil kayaker "
            f"fighting back on day {day} of a banana shelter defense game. "
            f"Under 80 chars, exclamation mark."
        )
    else:
        return None
    
    return _make_gemini_request(prompt, temperature=0.8)


def generate_victory_message(coins, days):
    """
    Generate a personalized victory message.
    """
    config = load_config()
    if not config.get("ai_storytelling"):
        return None
    
    prompt = (
        f"A player has defended their banana shelter for {days} days "
        f"and collected {coins} coins from evil kayakers. "
        f"Write ONE congratulatory sentence that's weird, rewarding, "
        f"and involves bananas. Under 100 chars."
    )
    
    return _make_gemini_request(prompt, temperature=0.8)


def get_dynamic_kayaker_name(day, static_names):
    """
    Get a kayaker name — tries AI first, falls back to static list.
    """
    config = load_config()
    if config.get("ai_kayaker_names"):
        name = generate_kayaker_name(day)
        if name:
            return name
    return random.choice(static_names)


def is_ai_available():
    """Check if the configured provider's API key is available."""
    config = load_config()
    provider = config.get("provider", "openrouter")

    if provider == "openrouter":
        or_key = get_openrouter_active_key()
        return bool(or_key)

    # Gemini path
    api_key = get_api_key()
    if not api_key:
        return False

    # Quick validation — just check key format (starts with "AI")
    return api_key.startswith("AI")


def test_api_connection():
    """
    Test the active provider's API connection.
    Returns (success: bool, message: str)
    """
    config = load_config()
    provider = config.get("provider", "openrouter")

    if provider == "openrouter":
        from openrouter_bridge import test_openrouter_connection
        return test_openrouter_connection()
    else:
        # Gemini path
        api_key = get_api_key()
        if not api_key:
            return False, "No Gemini API key configured. Run: python3 config_manager.py"

        if not api_key.startswith("AI"):
            return False, "Gemini API key doesn't look valid (should start with 'AI...')"

        # Try a minimal request
        result = _make_gemini_request("Say exactly: OK", temperature=0.1)
        if result and "OK" in result:
            return True, "✅ Gemini API connection successful!"
        elif result:
            return True, f"✅ Connected! (Got: {result[:50]})"
        else:
            return False, "❌ Could not reach Gemini API. Check your key and internet."


if __name__ == "__main__":
    print("\n  🧪 Gemini Integration Test\n")
    success, msg = test_api_connection()
    print(f"  {msg}\n")
    
    if success:
        print("  🎭 Testing AI kayaker name...")
        name = generate_kayaker_name(1)
        if name:
            print(f"     → {name}")
        
        print("  📖 Testing scavenge description...")
        desc = generate_scavenge_description()
        if desc:
            print(f"     → {desc}")
