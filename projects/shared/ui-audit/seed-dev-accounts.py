#!/usr/bin/env python3
"""Seed dev audit accounts for all server-backed apps in manifest.json."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = Path(__file__).resolve().parent.parent.parent.parent  # repo root (~/…)
MANIFEST = ROOT / "manifest.json"


def run(cmd, cwd):
    print(f"  $ {cmd}")
    subprocess.run(cmd, shell=True, cwd=cwd, check=False)


def main():
    data = json.loads(MANIFEST.read_text())
    for app in data["apps"]:
        if not app.get("seed"):
            continue
        proj = WORKSPACE / app["project"]
        if not proj.is_dir():
            print(f"SKIP {app['id']}: missing {proj}")
            continue
        print(f"Seed {app['id']} …")
        run(app["seed"].replace("{port}", str(app["port"])), proj)
    print("Done.")


if __name__ == "__main__":
    main()
