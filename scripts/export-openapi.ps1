<#
.SYNOPSIS
  Export the Forge/CodeMonkeys API's OpenAPI schema as a versioned artifact.

.DESCRIPTION
  Imports server.py (no network call - FastAPI builds the schema from the
  live route table in-process) and writes it as pretty-printed JSON to
  dist/openapi/openapi-<version>.json plus a stable openapi-latest.json
  alias, so API consumers/typed-client generators have something to diff
  against release over release.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/export-openapi.ps1
#>
[CmdletBinding()]
param(
    [string]$OutDir = "dist/openapi"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$exportScript = @"
import json, os, sys
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DATA_DIR', os.path.join(os.getcwd(), 'data'))
import server

schema = server.app.openapi()
version = schema.get('info', {}).get('version', '0.0.0')
out_dir = sys.argv[1]
versioned = os.path.join(out_dir, f'openapi-{version}.json')
latest = os.path.join(out_dir, 'openapi-latest.json')
with open(versioned, 'w', encoding='utf-8') as f:
    json.dump(schema, f, indent=2, sort_keys=True)
with open(latest, 'w', encoding='utf-8') as f:
    json.dump(schema, f, indent=2, sort_keys=True)
print(f'Wrote {versioned}')
print(f'Wrote {latest}')
paths = schema.get('paths', {})
print(f'{len(paths)} paths')
"@

$TmpScript = Join-Path ([System.IO.Path]::GetTempPath()) ("cm_export_openapi_" + [guid]::NewGuid().ToString() + ".py")
Set-Content -NoNewline -Encoding utf8 -Path $TmpScript -Value $exportScript
try {
    & $Python $TmpScript $OutDir
    if ($LASTEXITCODE -ne 0) {
        throw "openapi export failed (exit $LASTEXITCODE)"
    }
} finally {
    if (Test-Path $TmpScript) {
        [System.IO.File]::Delete($TmpScript)
    }
}

Write-Host ""
Write-Host "OK - schema exported to $OutDir" -ForegroundColor Green
