# One-time Vertex setup — Windows (PowerShell)
# Run:  powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cfg = Join-Path $env:APPDATA "codemonkeys"
$CursorRules = Join-Path $env:USERPROFILE ".cursor\rules"

Write-Host "== Vertex GCP credits setup (codemonkeys-498819) =="
New-Item -ItemType Directory -Force -Path $Cfg | Out-Null
$EnvFile = Join-Path $Cfg "vertex.env"
if (-not (Test-Path $EnvFile)) {
  Copy-Item (Join-Path $Root "vertex.env.example") $EnvFile
  Write-Host "Wrote $EnvFile"
} else {
  Write-Host "Keeping existing $EnvFile"
}

New-Item -ItemType Directory -Force -Path $CursorRules | Out-Null
Copy-Item (Join-Path $Root "cursor-rule-vertex-gcp-credits.mdc") (Join-Path $CursorRules "vertex-gcp-credits.mdc") -Force
Write-Host "Installed Cursor rule -> $CursorRules\vertex-gcp-credits.mdc"

$SaPath = Join-Path $Cfg "vertex-sa.json"
if (Test-Path $SaPath) {
  Write-Host "Service account already at $SaPath"
} elseif ($env:VERTEX_SA_SRC -and (Test-Path $env:VERTEX_SA_SRC)) {
  Copy-Item $env:VERTEX_SA_SRC $SaPath
  Add-Content $EnvFile "GOOGLE_APPLICATION_CREDENTIALS=$SaPath"
  Write-Host "Installed SA from VERTEX_SA_SRC"
} elseif (Get-Command gcloud -ErrorAction SilentlyContinue) {
  Write-Host "Running: gcloud auth application-default login (browser)"
  gcloud auth application-default login --project=codemonkeys-498819
} else {
  Write-Host ""
  Write-Host "No gcloud CLI. Either:"
  Write-Host "  1) Install Google Cloud SDK, re-run this script, OR"
  Write-Host "  2) Download SA JSON from GCP Console -> save as:"
  Write-Host "     $SaPath"
  Write-Host "     then add: GOOGLE_APPLICATION_CREDENTIALS=$SaPath"
}

Write-Host ""
Write-Host "Verify:"
python (Join-Path $Root "verify_vertex.py")
if ($LASTEXITCODE -ne 0) {
  Write-Host "Install deps: pip install google-auth"
  exit 1
}
Write-Host ""
Write-Host "Done. Pull same git repos on Linux -> run setup.sh once there."
