<#
.SYNOPSIS
  Build the CodeMonkeys Windows installer (NSIS setup .exe).

.DESCRIPTION
  Step 1 — Run build-windows.ps1 (PyInstaller onedir).
  Step 2 — Run NSIS (makensis) to pack dist/CodeMonkeys/ into a setup .exe.
  Step 3 — Place final installer in dist/installers/.

  Requires NSIS 3.x installed and on PATH, or at the path in $Makensis.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/build-installer.ps1
  powershell -ExecutionPolicy Bypass -File scripts/build-installer.ps1 -SkipPyInstaller
#>

[CmdletBinding()]
param(
    [switch]$SkipPyInstaller
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

# ---- Detect makensis ------------------------------------------------
$MakensisCandidates = @(
    "makensis"
    "${env:ProgramFiles}\NSIS\makensis.exe"
    "${env:ProgramFiles(x86)}\NSIS\makensis.exe"
)
$Makensis = $null
foreach ($cand in $MakensisCandidates) {
    $exe = Get-Command $cand -ErrorAction SilentlyContinue
    if ($exe) { $Makensis = $exe.Source; break }
}
if (-not $Makensis) {
    throw "NSIS (makensis) not found. Install NSIS 3.x from https://nsis.sourceforge.io and ensure it is on PATH."
}

Write-Host "==> CodeMonkeys Desktop installer build" -ForegroundColor Cyan
Write-Host ("    root:     {0}" -f $Root)
Write-Host ("    makensis: {0}" -f $Makensis)

# ---- Step 1: PyInstaller --------------------------------------------
if (-not $SkipPyInstaller) {
    Write-Host "==> Step 1 / 2:  PyInstaller bundle" -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "build-windows.ps1")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }
} else {
    Write-Host "==> Step 1 / 2:  SKIPPED (--SkipPyInstaller)" -ForegroundColor Yellow
}

$DistPath = Join-Path $Root "dist\CodeMonkeys"
if (-not (Test-Path $DistPath)) {
    throw ("PyInstaller output not found at {0}. Run build-windows.ps1 first, or omit -SkipPyInstaller." -f $DistPath)
}

# ---- Step 2: NSIS ---------------------------------------------------
Write-Host "==> Step 2 / 2:  NSIS installer" -ForegroundColor Cyan

$InstallersDir = Join-Path $Root "dist\installers"
if (-not (Test-Path $InstallersDir)) {
    New-Item -ItemType Directory -Path $InstallersDir -Force | Out-Null
}

$Spec = Join-Path $Root "desktop\installer.nsi"
Write-Host ("    spec: {0}" -f $Spec)

# makensis needs to be invoked from the repo root because the .nsi
# references dist/CodeMonkeys/ and desktop/codemonkeys.ico with
# relative paths resolvable from cwd.
& $Makensis $Spec
if ($LASTEXITCODE -ne 0) { throw "NSIS build failed" }

# ---- Report ----------------------------------------------------------
Write-Host ""
Write-Host "OK - installer created:" -ForegroundColor Green
Get-ChildItem $InstallersDir -Filter "*.exe" | ForEach-Object {
    Write-Host ("  {0}  ({1:N0} bytes)" -f $_.FullName, $_.Length)
}
