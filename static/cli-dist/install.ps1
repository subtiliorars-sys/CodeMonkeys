# Installs the CodeMonkeys terminal CLI from a running CodeMonkeys server.
#
#   irm https://codemonkeys.fly.dev/static/cli-dist/install.ps1 | iex
#
# Override the source server with $env:CM_SERVER before running, e.g. for a
# self-hosted instance.
$ErrorActionPreference = "Stop"

$CmServer = if ($env:CM_SERVER) { $env:CM_SERVER } else { "https://codemonkeys.fly.dev" }
$WheelUrl = "$($CmServer.TrimEnd('/'))/static/cli-dist/codemonkeys_cli-0.1.3-py3-none-any.whl"

$tmp = Join-Path $env:TEMP "codemonkeys-cli-install"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
# Keep the real wheel filename (version + tags) - 'uv tool install' rejects a
# generic renamed filename ("Must have a version"), unlike pip which is lenient.
$wheelName = [System.IO.Path]::GetFileName($WheelUrl)
$wheelPath = Join-Path $tmp $wheelName

Write-Host "Fetching CLI wheel from $WheelUrl ..."
Invoke-WebRequest -Uri $WheelUrl -OutFile $wheelPath

# Prefer 'uv tool install' when available: an isolated install that never
# touches the system/managed Python, so it works even when pip refuses with
# "externally-managed-environment" (e.g. a uv-managed or distro-managed
# Python - PEP 668). Falls back to pip --user otherwise.
function Test-Uv {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { return $false }
    try { & uv --version *> $null; return $LASTEXITCODE -eq 0 } catch { return $false }
}

$installed = $false
if (Test-Uv) {
    Write-Host "Installing with 'uv tool install' (isolated) ..."
    & uv tool install $wheelPath --force
    if ($LASTEXITCODE -eq 0) {
        $installed = $true
    } else {
        Write-Host "uv install failed; falling back to pip ..."
    }
}

if (-not $installed) {
    # Get-Command finds Windows' python.exe "App Execution Alias" stub even when
    # no real Python is installed, so probe by actually running it.
    function Test-RealPython($name) {
        if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { return $false }
        try { & $name --version *> $null; return $LASTEXITCODE -eq 0 } catch { return $false }
    }
    $py = if (Test-RealPython "python3") { "python3" } elseif (Test-RealPython "python") { "python" } else { $null }
    if (-not $py) {
        Write-Error "Neither 'uv' nor a real 'python' (3.10+) was found on PATH. Install uv (https://astral.sh/uv) - recommended, no system-Python conflicts - or Python from python.org / 'winget install Python.Python.3.12'. If 'python --version' prints a Microsoft Store prompt, disable that alias under Settings > Apps > Advanced app settings > App execution aliases."
        exit 1
    }

    Write-Host "Installing with pip (--user) ..."
    & $py -m pip install --user --upgrade $wheelPath
    if ($LASTEXITCODE -ne 0) {
        Write-Error "pip install failed. If the error says 'externally-managed-environment', this Python is managed by uv/your OS and blocks --user installs by design (PEP 668) - install uv (https://astral.sh/uv) and re-run this script instead."
        exit 1
    }
    $installed = $true
}

Write-Host ""
Write-Host "Installed. Run:"
Write-Host "  monkey --server $CmServer"
Write-Host "('cm' and 'codemonkeys' also work, same command)"
Write-Host "(first run prompts for username + MFA code, then caches the token in ~/.codemonkeys/cli.json)"
Write-Host ""
Write-Host "If the command isn't found: pip installs put it under your Python user-scripts dir"
Write-Host "(python -m site --user-base, then add its Scripts subfolder to PATH); uv installs put it"
Write-Host "under uv's tool shims dir (run 'uv tool update-shell' then restart your terminal)."

Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
