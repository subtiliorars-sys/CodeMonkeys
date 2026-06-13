#!/usr/bin/env python3
"""Verify Vertex AI works on this machine (Linux / macOS / Windows)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vertex_env  # noqa: E402

vertex_env.load_env()


def main() -> int:
    print("Vertex portable check")
    print("  config dir:", vertex_env.config_dir())
    print("  project:  ", vertex_env.project())
    print("  region:   ", vertex_env.region())
    print("  creds ok: ", vertex_env.credentials_ready())
    if not vertex_env.credentials_ready():
        print("\nFAIL: No credentials. Run setup.sh or setup.ps1 once on this machine.")
        return 1
    try:
        import google.auth
        import google.auth.transport.requests as gar
    except ImportError:
        print("\nFAIL: pip install google-auth")
        return 1
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(gar.Request())
    url = (
        f"https://{vertex_env.region()}-aiplatform.googleapis.com/v1/projects/"
        f"{vertex_env.project()}/locations/{vertex_env.region()}/endpoints/openapi/chat/completions"
    )
    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [{"role": "user", "content": "Reply exactly: VERTEX_OK"}],
        "max_tokens": 8,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"\nFAIL: HTTP {e.code}\n{e.read().decode()[:500]}")
        return 1
    usage = data.get("usage") or {}
    print(f"\nOK: Vertex reachable ({usage.get('total_tokens', '?')} tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
