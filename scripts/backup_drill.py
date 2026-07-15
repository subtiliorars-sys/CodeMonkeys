#!/usr/bin/env python3
"""M-8 backup posture — restore drill + receipt (GOVERNANCE.md M-8).

Reads back and validates every structured store CodeMonkeys writes under
DATA_DIR — JSON parse + expected shape, JSONL line-parse, encrypted-config
(CMENC1) decrypt under the current master key, S-3 audit-chain integrity,
sessions tree — and appends a timestamped receipt to
backup_drill_receipts.jsonl inside the drilled tree. Owner-viewable history:
GET /api/backup/drill-history (or trigger remotely: POST /api/backup/drill).

Run on the server (fly ssh console -a codemonkeys):
  python scripts/backup_drill.py                  # drill the live DATA_DIR (/data)

Or run the REAL restore drill against a restored snapshot: restore the Fly
volume snapshot to a new volume (fly volumes snapshots list cm_data → fly
volumes create --snapshot-id ...) or copy /data down (fly ssh sftp), then:
  python scripts/backup_drill.py <path-to-restored-data-dir>

Exit code: 0 = every store read back clean, 1 = at least one store failed.
Uses server.run_backup_drill() so the CLI and the owner endpoint never drift.
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

    data_dir = sys.argv[1] if len(sys.argv) > 1 else None
    result = server.run_backup_drill(by="cli", data_dir=data_dir)
    print(json.dumps(result, indent=2))
    if result.get("ok"):
        print(f"OK — {result['checked']} store(s) read back clean "
              f"({result['absent']} absent); receipt appended.", file=sys.stderr)
        return 0
    print(f"RESTORE DRILL FAILED — store(s) {result['failed']} did not read "
          "back; see 'stores' above. Receipt appended.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
