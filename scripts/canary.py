#!/usr/bin/env python3
"""
canary.py — runtime process/network canary for CodeMonkeys dev sessions.

Run this in a background tab WHILE the app server is running:
    python scripts/canary.py --port 8080   # watch a specific listener
    python scripts/canary.py              # watch all python/node/chromium procs

It polls every 5s and prints a warning if any monitored process:
  - opens a connection to a known-bad port (exfil C2: 4444, 1337, 4443, 5555, 7001)
  - connects to a known-malicious IP range (starter blocklist)
  - spawns an unusual child (bash, sh, powershell, netcat) from app processes

This is a *detector*, not a guard — it alerts, doesn't kill. Review alerts
before acting. Stdlib only (psutil optional for richer detail; gracefully
degrades if psutil is not installed).
"""

import argparse
import time
import socket
import sys

POLL_INTERVAL = 5  # seconds

# Ports commonly used by malware C2 / reverse shells.
BAD_PORTS = {4444, 1337, 4443, 5555, 7001, 9001, 444, 1389}

# Processes we watch (app-layer); if any of these spawns a shell-ish child, alert.
WATCH_PROCS = {"python", "python3", "node", "chromium", "chrome", "CodeMonkeys"}

# Shell-ish children we consider suspicious when spawned BY watched procs.
SUSPICIOUS_CHILDREN = {"bash", "sh", "powershell", "sh.exe", "cmd.exe", "nc",
                       "netcat", "ncat", "socat", "curl", "wget", "powershell.exe"}

# Known-bad outbound IP prefixes (starter blocklist; refresh from
# https://www.spamhaus.org/drop/ or abuse.ch periodically).
KNOWN_BAD_PREFIXES = (
    "185.53.177.",
    "45.146.164.",
    "188.25.99.",
    "91.210.104.",
)


def have_psutil():
    """Optional dependency for richer process tree introspection."""
    try:
        import psutil  # noqa: F401
        return True
    except ImportError:
        return False


def _pid_name(pid):
    """Best-effort process name lookup (psutil-aware)."""
    try:
        import psutil
        return psutil.Process(pid).name()
    except Exception:
        pass
    # Fallback: /proc/<pid>/comm on Linux
    try:
        with open("/proc/%d/comm" % pid) as f:
            return f.read().strip()
    except Exception:
        return str(pid)


def check_connections_psutil():
    """Rich connection scan scanning all inet connections."""
    import psutil
    for conn in psutil.net_connections(kind="inet"):
        if conn.status == psutil.CONN_NONE:
            continue
        if conn.raddr and conn.raddr.port in BAD_PORTS:
            print("[canary] WARNING: %s (pid %s) -> %s:%s (known-bad port)"
                  % (_pid_name(conn.pid), conn.pid, conn.raddr.ip, conn.raddr.port))
        if conn.raddr and conn.raddr.ip.startswith(KNOWN_BAD_PREFIXES):
            print("[canary] WARNING: %s (pid %s) -> %s:%s (known-bad prefix)"
                  % (_pid_name(conn.pid), conn.pid, conn.raddr.ip, conn.raddr.port))


def check_children_psutil():
    """Detect suspicious child processes spawned by watched app processes."""
    import psutil
    for p in psutil.process_iter(["name", "pid"]):
        try:
            base = p.info["name"].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            if base.lower() not in WATCH_PROCS:
                continue
            for c in p.children(recursive=False):
                try:
                    cbase = c.name().rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                except Exception:
                    continue
                if cbase.lower() in SUSPICIOUS_CHILDREN:
                    print("[canary] WARNING: %s(pid %d) spawned %s(pid %d)"
                          % (base, p.info["pid"], cbase, c.pid))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def check_connections_fallback():
    """No psutil? Try /proc/net/tcp (Linux) — no-op on Windows/macOS."""
    if not sys.platform.startswith("linux"):
        return
    try:
        with open("/proc/net/tcp") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 4 or parts[0] == "sl":
                    continue
                remote = parts[2]
                state = parts[3]
                if state != "01":  # 01 = ESTABLISHED
                    continue
                ip_hex, port_hex = remote.split(":")
                port = int(port_hex, 16)
                if port in BAD_PORTS:
                    ip = socket.inet_ntoa(bytes.fromhex(ip_hex))
                    print("[canary] WARNING: connection to %s:%d (known-bad port)"
                          % (ip, port))
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Runtime canary for CodeMonkeys dev")
    parser.add_argument("--watch-port", type=int, help="alert if this specific listener opens")
    parser.parse_args()

    using_psutil = have_psutil()
    mode = "rich (psutil)" if using_psutil else "basic (/proc/net only on Linux)"
    print("[canary] started — watching %s | bad_ports=%s | mode=%s"
          % (", ".join(sorted(WATCH_PROCS)), sorted(BAD_PORTS), mode))
    print("[canary] press Ctrl-C to stop.\n")
    try:
        while True:
            if using_psutil:
                check_connections_psutil()
                check_children_psutil()
            else:
                check_connections_fallback()
            time.sleep(POLL_INTERVAL)
    except KeyboardInterrupt:
        print("\n[canary] stopped.")


if __name__ == "__main__":
    main()
