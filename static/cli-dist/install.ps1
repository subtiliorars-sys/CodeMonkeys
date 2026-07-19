# Installs the CodeMonkeys terminal CLI from a running CodeMonkeys server.
#
#   irm https://codemonkeys.fly.dev/static/cli-dist/install.ps1 | iex
#
# Override the source server with $env:CM_SERVER before running, e.g. for a
# self-hosted instance.
$ErrorActionPreference = "Stop"

$CmServer = if ($env:CM_SERVER) { $env:CM_SERVER } else { "https://codemonkeys.fly.dev" }
$WheelUrl = "$($CmServer.TrimEnd('/'))/static/cli-dist/codemonkeys_cli-0.1.1-py3-none-any.whl"

# Get-Command finds Windows' python.exe "App Execution Alias" stub even when no
# real Python is installed, so probe by actually running it rather than trusting
# Get-Command alone.
function Test-RealPython($name) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { return $false }
    try { & $name --version *> $null; return $LASTEXITCODE -eq 0 } catch { return $false }
}
$py = if (Test-RealPython "python3") { "python3" } elseif (Test-RealPython "python") { "python" } else { $null }
if (-not $py) {
    Write-Error "python (3.10+) is required but was not found on PATH. If 'python --version' prints a Microsoft Store prompt, disable that alias under Settings > Apps > Advanced app settings > App execution aliases, then install Python from python.org or 'winget install Python.Python.3.12'."
    exit 1
}

$tmp = Join-Path $env:TEMP "codemonkeys-cli-install"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$wheelPath = Join-Path $tmp "codemonkeys_cli.whl"

Write-Host "Fetching CLI wheel from $WheelUrl ..."
Invoke-WebRequest -Uri $WheelUrl -OutFile $wheelPath

Write-Host "Installing with pip (--user) ..."
& $py -m pip install --user --upgrade $wheelPath

Write-Host ""
Write-Host "Installed. Run:"
Write-Host "  cm --server $CmServer"
Write-Host "('codemonkeys' also works, if you prefer the full name)"
Write-Host "(first run prompts for username + MFA code, then caches the token in ~/.codemonkeys/cli.json)"
Write-Host ""
Write-Host "If 'codemonkeys' isn't found, make sure your Python user Scripts dir is on PATH"
Write-Host "(python -m site --user-base, then add its Scripts subfolder)."

Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
