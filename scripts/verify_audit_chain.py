#!/usr/bin/env python3
"""S-3 (issue #68) — verify the hash-chained tamper-evident audit trail.

Walks DATA_DIR/audit_chain.jsonl, recomputes every entry's SHA-256, checks the
seq/prev links, and cross-checks the tail against audit_chain.head.json.
Detects mutation, deletion, insertion, reordering, and tail truncation.

Run on the server (fly ssh console -a <app>) or locally against a copied /data:
  python scripts/verify_audit_chain.py                    # DATA_DIR (or /data, or ./data)
  python scripts/verify_audit_chain.py <chain.jsonl> [<head.json>]

Exit code: 0 = chain verifies clean, 1 = tampering/damage detected.

Uses server.verify_audit_chain() so the CLI and the owner endpoint
(/api/audit/verify) can never drift apart.
"""
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_data_dir() -> str:
    if os.environ.get("DATA_DIR"):
        return os.environ["DATA_DIR"]
    return "/data" if os.path.isdir("/data") else os.path.join(_REPO_ROOT, "data")


def main() -> int:
    os.environ.setdefault("DATA_DIR", _default_data_dir())
    sys.path.insert(0, _REPO_ROOT)
    import server  # noqa: E402  (imports after DATA_DIR is pinned, like tests do)

    chain_path = sys.argv[1] if len(sys.argv) > 1 else None
    head_path = sys.argv[2] if len(sys.argv) > 2 else None
    result = server.verify_audit_chain(chain_path, head_path)
    print(json.dumps(result, indent=2))
    if result.get("ok"):
        print(f"OK — {result['entries']} entrie(s), chain intact.", file=sys.stderr)
        return 0
    print("TAMPER-EVIDENT FAILURE — see 'error' above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
