"""Portable Vertex / GCP env loader — Linux, macOS, Windows.

Used by CodeMonkeys server, vertex_burn.py, and verify_vertex.py.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home())
        return base / "codemonkeys"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg) if xdg else Path.home() / ".config"
    return root / "codemonkeys"


def env_file_paths(extra_dirs: list[Path] | None = None) -> list[Path]:
    paths = [config_dir() / "vertex.env"]
    if extra_dirs:
        for d in extra_dirs:
            paths.extend([d / "vertex.env", d / ".vertex.env"])
    return paths


def load_env(extra_dirs: list[Path] | None = None) -> Path | None:
    """Load vertex.env files; return path loaded or None."""
    loaded = None
    for path in env_file_paths(extra_dirs):
        if not path.is_file():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
        loaded = path
    cfg = config_dir()
    sa = cfg / "vertex-sa.json"
    if sa.is_file() and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa)
    raw = os.environ.get("VERTEX_CREDENTIALS_JSON", "").strip()
    if raw and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            json.loads(raw)
            cfg.mkdir(parents=True, exist_ok=True)
            sa.write_text(raw)
            sa.chmod(0o600)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(sa)
        except json.JSONDecodeError:
            pass
    return loaded


def project() -> str:
    return os.environ.get("GOOGLE_CLOUD_PROJECT", "codemonkeys-498819")


def region() -> str:
    return os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")


def adc_path() -> Path | None:
    if os.name == "nt":
        p = Path(os.environ.get("APPDATA", "")) / "gcloud" / "application_default_credentials.json"
    else:
        p = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    return p if p.is_file() else None


def credentials_ready() -> bool:
    gac = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if gac and Path(gac).is_file():
        return True
    if os.environ.get("VERTEX_CREDENTIALS_JSON", "").strip():
        return True
    if (config_dir() / "vertex-sa.json").is_file():
        return True
    return adc_path() is not None
