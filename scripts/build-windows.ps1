<#
.SYNOPSIS
  Build a deployable Windows desktop app for CodeMonkeys (PyInstaller onedir).

.DESCRIPTION
  Produces dist/CodeMonkeys/CodeMonkeys.exe - a native WebView2 shell around
  the existing FastAPI + Forge UI. Requires Python 3.12+, pip, and WebView2
  Runtime (preinstalled on modern Windows 10/11).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$Console
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

Write-Host "==> CodeMonkeys Windows build" -ForegroundColor Cyan
Write-Host ("    root: {0}" -f $Root)

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

if (-not $SkipInstall) {
    Write-Host "==> Installing desktop requirements"
    & $Python -m pip install -r requirements-desktop.txt
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
}

$Dist = Join-Path $Root "dist\CodeMonkeys"
$Build = Join-Path $Root "build\codemonkeys"
if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
if (Test-Path $Build) { Remove-Item -Recurse -Force $Build }

$Spec = Join-Path $Root "desktop\codemonkeys.spec"
Write-Host ("==> PyInstaller ({0})" -f $Spec)
& $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $Root "dist") --workpath $Build $Spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Exe = Join-Path $Dist "CodeMonkeys.exe"
if (-not (Test-Path $Exe)) {
    throw ("Build failed - missing {0}" -f $Exe)
}

$Readme = Join-Path $Dist "README.txt"
$ReadmeBody = @"
CodeMonkeys - Windows desktop
=============================

Run:  CodeMonkeys.exe

Data and workspace:  %APPDATA%\codemonkeys\data
Loopback server:   http://127.0.0.1:<port>/  (port chosen at launch)

First run: register the Owner account (PIN + TOTP), then add your API keys
under Settings -> Models and keys (bring-your-own-key). Owner can later invite
users and (optionally) grant Vertex/GCP credits.

Requires Microsoft Edge WebView2 Runtime (usually already on Win10/11):
  https://developer.microsoft.com/microsoft-edge/webview2/

Dev / headless smoke:
  CodeMonkeys.exe --no-window
  or:  python -m desktop --no-window
"@
Set-Content -Path $Readme -Value $ReadmeBody -Encoding ASCII

Write-Host ""
Write-Host "OK - packaged app:" -ForegroundColor Green
Write-Host ("  {0}" -f $Exe)
Write-Host "Zip the folder for distribution:"
Write-Host ("  Compress-Archive -Path '{0}' -DestinationPath 'dist\CodeMonkeys-windows.zip'" -f $Dist)
