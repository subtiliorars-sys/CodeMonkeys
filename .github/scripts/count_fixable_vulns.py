"""Count pip-audit findings that have a known fix version available.

Split out of .github/workflows/ci.yml's inline `run:` block - a multi-line
python -c string embedded in a YAML block scalar is fragile (indentation
drift silently terminates the YAML block early, which is exactly what broke
CI here: see git history on this file). A real script file has no such
failure mode and is testable on its own.

Usage: python3 count_fixable_vulns.py <pip-audit-json-file>
Prints the count of vulnerabilities that have at least one fix_versions entry.
"""
import json
import sys


def count_fixable(data: dict) -> int:
    return sum(
        1
        for dep in data.get("dependencies", [])
        if dep.get("vulns")
        and any(vuln.get("fix_versions") for vuln in dep["vulns"])
    )


if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        data = json.load(f)
    print(count_fixable(data))
