# Dependency vulnerability audit — triage flow

CI runs `pip-audit` (OSV-backed) against `requirements.txt` and
`requirements-desktop.txt` on every push/PR (`.github/workflows/ci.yml`,
`dependency-audit` job). It fails the build on **any** known CVE/GHSA in a
resolved dependency version — that's the severity threshold: zero-tolerance
for a known-vulnerable pin, not a CVSS-score cutoff. Reproduce locally:

```powershell
pip install pip-audit
pip-audit -r requirements.txt
pip-audit -r requirements-desktop.txt
```

## When the job goes red

1. **Read the finding** — `pip-audit` prints the package, installed version,
   the CVE/GHSA ID, and (usually) the first fixed version.
2. **Check whether the vulnerable code path is even reachable here.** Not
   every CVE in a dependency applies to how CodeMonkeys uses it (e.g. a CVE
   in an HTTP server component of a library CodeMonkeys only uses as a
   client). Read the advisory before assuming impact.
3. **Fix — prefer upgrading first:**
   - Bump the pin in `requirements.txt` / `requirements-desktop.txt` to the
     fixed version (or later).
   - `pip install -r requirements.txt` locally, then `python -c "import
     server"` and `python -m pytest tests/ -q` — a version bump is a real
     dependency change, verify it same as any other.
   - Re-run `pip-audit` to confirm the finding clears.
4. **If no fix is available yet, or upgrading breaks compatibility:**
   document why in the PR that touches the pin (not silently), and consider
   whether the vulnerable path can be avoided in code instead. Do not
   silently pin around a scanner without a documented reason — that defeats
   the point of the gate.
5. **Do not suppress/ignore a finding** (e.g. `--ignore-vuln`) without a
   comment in `requirements.txt` next to the pin explaining why it's safe to
   ignore (unreachable code path, disputed CVE, etc.) and, ideally, a
   tracking issue to revisit.

## Why pip-audit over safety

`pip-audit` is the PyPA-maintained tool, uses the OSV database (broader/more
current coverage than PyPI Advisory alone), and needs no API key/account —
important for an unattended CI job. No functional reason ruled out `safety`;
either would satisfy this issue's acceptance criteria.
