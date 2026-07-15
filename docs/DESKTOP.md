# CodeMonkeys — Windows desktop

Native Windows shell around the existing FastAPI + Forge console.

## Product shape (owner intent)

| Surface | Who | Model keys | Why |
|---------|-----|------------|-----|
| **Windows desktop (this)** | You / trusted machines | Owner pastes keys; optional Vertex credit grants | Full agent + local workspace; admin control |
| **Public web (later)** | Anyone | **Bring-your-own-key (BYOK)** | Free to use — no shared credits to protect |
| **Hosted Fly (today)** | Owner + invited members | Shared Owner keys on volume | Keep for remote/Chromebook until desktop is solid |

Security that actually matters for credits: **Owner auth** (PIN + TOTP) so only
you can attach Vertex/GCP credits or invite people onto a credit-backed instance.
Everyone else pastes their own provider key in **Settings → Models & keys**.

## Dev run (from repo root)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-desktop.txt
python -m desktop
```

Headless smoke (no WebView window):

```powershell
python -m desktop --no-window
# then browse http://127.0.0.1:<port>/  (port printed / in %APPDATA% path note)
```

Data directory: `%APPDATA%\codemonkeys\data`  
Workspace: `%APPDATA%\codemonkeys\data\workspace`

## Package a deployable app

### Quick zip (no installer)

```powershell
pwsh scripts/build-windows.ps1
# → dist\CodeMonkeys\CodeMonkeys.exe
Compress-Archive -Path dist\CodeMonkeys -DestinationPath dist\CodeMonkeys-windows.zip
```

### Windows installer (NSIS) — recommended

```powershell
pwsh scripts/build-installer.ps1
# → dist\CodeMonkeys\CodeMonkeys.exe       (PyInstaller onedir)
# → dist\installers\CodeMonkeys-Desktop-Setup-0.2.0.exe  (NSIS setup)
```

The installer:
- Copies `dist/CodeMonkeys/` to `%PROGRAMFILES64%\CodeMonkeys`
- Creates **Start Menu** → CodeMonkeys → CodeMonkeys Desktop
- Creates a **Desktop** shortcut
- Registers in **Add/Remove Programs** (for clean uninstall)
- Writes `HKLM\Software\Microsoft\Windows\CurrentVersion\App Paths`
- Embeds version info (`0.2.0`) in the setup .exe

Requires **NSIS 3.x** ([nsis.sourceforge.io](https://nsis.sourceforge.io)) and
**Microsoft Edge WebView2 Runtime** (already on most Win10/11 installs).

### Icon conversion (PNG → ICO)

The source icon lives at `desktop/icon.svg`.  Convert to `.ico` for PyInstaller
and NSIS packaging:

```powershell
# Inkscape → PNG, then ImageMagick → ICO with multiple sizes:
inkscape desktop/icon.svg --export-filename desktop/icon-256.png -w 256
magick convert desktop/icon-256.png -define icon:auto-resize=256,64,48,32,16 desktop/codemonkeys.ico
```

Drop the resulting `desktop/codemonkeys.ico` file — the `.spec` and `.nsi`
files reference it by that name.

## First run

1. Launch `CodeMonkeys.exe` (or `python -m desktop`)
2. Register the **Owner** account → scan TOTP QR
3. Settings → Models & keys → paste Gemini / OpenRouter / Anthropic / etc.
4. Clone a repo into the workspace and code

Invites + Vertex credit grants stay Owner-only — same as the Fly app.

## Why desktop before a polished public web

- Agents need a real filesystem and shell; desktop owns that without Fly volume gymnastics
- Loopback-only bind (`127.0.0.1`) shrinks the network attack surface vs a public URL
- Same `server.py` + `static/forge/` — web and desktop stay one codebase
- Public BYOK web can ship later as the same UI pointed at a multi-user host, without
  exposing your API credits

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Window never opens | Install WebView2 Runtime; or open the printed `http://127.0.0.1:…` URL in a browser |
| Port in use | Launcher picks the next free port from 8765 |
| Locked out of Owner | Same recovery as Fly: `scripts/reset_access.py` against `%APPDATA%\codemonkeys\data` |
| Import errors after pull | `pip install -r requirements-desktop.txt` |
