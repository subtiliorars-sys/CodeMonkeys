#!/usr/bin/env python3
"""Burn GCP Vertex credits on game + revenue build work.

Portable: Linux, macOS, Windows — see projects/shared/vertex-credits/README.md

  ./scripts/vertex_burn.py --list
  ./scripts/vertex_burn.py --all
  ./scripts/vertex_burn.py --job freak-franchise-expand
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT.parent.parent / "shared" / "vertex-credits"
sys.path.insert(0, str(SHARED))
import vertex_env  # noqa: E402

vertex_env.load_env(extra_dirs=[ROOT])
JOBS_FILE = Path(__file__).resolve().parent / "vertex_jobs.json"
DEFAULT_OUT = ROOT.parent / "PixelSports" / "docs" / "vertex-generated"
PROJECT = vertex_env.project()
REGION = vertex_env.region()


def _token() -> str:
    try:
        import google.auth
        import google.auth.transport.requests as gar
    except ImportError as exc:
        raise SystemExit("Install google-auth: .venv/bin/python -m pip install google-auth") from exc
    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(gar.Request())
    return creds.token


def vertex_chat(system: str, user: str, *, model: str, max_tokens: int = 8192) -> tuple[str, dict]:
    url = (f"https://{REGION}-aiplatform.googleapis.com/v1/projects/{PROJECT}"
           f"/locations/{REGION}/endpoints/openapi/chat/completions")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:800]
        raise RuntimeError(f"Vertex HTTP {e.code}: {body}") from e
    text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    usage = data.get("usage") or {}
    return text.strip(), usage


def load_jobs() -> list[dict]:
    with open(JOBS_FILE) as f:
        raw = json.load(f)
    return raw.get("jobs", raw) if isinstance(raw, dict) else raw


def run_job(job: dict, model: str, out_dir: Path, dry_run: bool) -> dict:
    jid = job["id"]
    out_path = out_dir / job.get("out", f"{jid}.md")
    context_files = job.get("context_files", [])
    context = ""
    for rel in context_files:
        p = Path(rel)
        if not p.is_absolute():
            p = ROOT.parent / rel
        if p.is_file():
            context += f"\n\n--- FILE: {p.name} ---\n{p.read_text()[:12000]}"
    user = job["prompt"]
    if context:
        user = job["prompt"] + "\n\nCONTEXT:" + context
    if dry_run:
        print(f"[dry-run] {jid} -> {out_path}")
        return {"id": jid, "skipped": True}
    print(f"Running {jid} ({model})…")
    t0 = time.time()
    text, usage = vertex_chat(
        job.get("system", "You are a game designer and revenue strategist."),
        user,
        model=model,
        max_tokens=int(job.get("max_tokens", 8192)),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    header = f"# {job.get('title', jid)}\n\n_Generated via Vertex `{model}` · project `{PROJECT}` · {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}_\n\n"
    out_path.write_text(header + text + "\n")
    elapsed = time.time() - t0
    meta = {"id": jid, "out": str(out_path), "usage": usage, "elapsed_s": round(elapsed, 1)}
    print(f"  wrote {out_path} ({usage.get('total_tokens', '?')} tokens, {elapsed:.1f}s)")
    return meta


def main():
    ap = argparse.ArgumentParser(description="Burn GCP Vertex credits on fleet build jobs")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--job", action="append", default=[])
    ap.add_argument("--model", default="google/gemini-2.5-flash")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not vertex_env.credentials_ready():
        print("No Vertex credentials on this machine.", file=sys.stderr)
        print("Run: projects/shared/vertex-credits/setup.sh (Linux) or setup.ps1 (Windows)",
              file=sys.stderr)
        return 1
    jobs = {j["id"]: j for j in load_jobs()}
    if args.list:
        for jid, j in jobs.items():
            print(f"{jid:30} {j.get('title', '')}")
        return
    selected = list(jobs.keys()) if args.all else args.job
    if not selected:
        ap.error("Pass --all or --job <id> (use --list)")
    out_dir = Path(args.out_dir)
    results = []
    for jid in selected:
        if jid not in jobs:
            print(f"Unknown job: {jid}", file=sys.stderr)
            continue
        results.append(run_job(jobs[jid], args.model, out_dir, args.dry_run))
    summary_path = out_dir / "_run_summary.json"
    if not args.dry_run and results:
        out_dir.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps({"project": PROJECT, "model": args.model, "results": results}, indent=2))
        print(f"Summary: {summary_path}")


if __name__ == "__main__":
    raise SystemExit(main() or 0)
