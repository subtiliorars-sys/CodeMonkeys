# Installs the CodeMonkeys terminal CLI from a running CodeMonkeys server.
#
#   irm https://codemonkeys.fly.dev/static/cli-dist/install.ps1 | iex
#
# Override the source server with $env:CM_SERVER before running, e.g. for a
# self-hosted instance.
$ErrorActionPreference = "Stop"

$CmServer = if ($env:CM_SERVER) { $env:CM_SERVER } else { "https://codemonkeys.fly.dev" }
$WheelUrl = "$($CmServer.TrimEnd('/'))/static/cli-dist/codemonkeys_cli-0.1.0-py3-none-any.whl"

if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command python3 -ErrorAction SilentlyContinue)) {
    Write-Error "python (3.10+) is required but was not found on PATH."
    exit 1
}
$py = if (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" } else { "python" }

$tmp = Join-Path $env:TEMP "codemonkeys-cli-install"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$wheelPath = Join-Path $tmp "codemonkeys_cli.whl"

Write-Host "Fetching CLI wheel from $WheelUrl ..."
Invoke-WebRequest -Uri $WheelUrl -OutFile $wheelPath

Write-Host "Installing with pip (--user) ..."
& $py -m pip install --user --upgrade $wheelPath

Write-Host ""
Write-Host "Installed. Run:"
Write-Host "  codemonkeys --server $CmServer"
Write-Host "(first run prompts for username + MFA code, then caches the token in ~/.codemonkeys/cli.json)"
Write-Host ""
Write-Host "If 'codemonkeys' isn't found, make sure your Python user Scripts dir is on PATH"
Write-Host "(python -m site --user-base, then add its Scripts subfolder)."

Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
