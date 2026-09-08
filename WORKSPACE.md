# Linux Workspace Organization

**Last Updated:** 2026-06-12  
**Structure:** Organized for fast access

---

## 📁 Directory Map

```
~/ (home)
├── screenshots/          ← 📸 YOUR SCREENSHOTS (first!)
├── projects/
│   ├── claude/           ← Claude's work (games, recovery, CodeMonkeys, etc.)
│   ├── gemini/           ← Gemini's work (OmniTender family)
│   └── shared/           ← Shared repos (agent-corps, fleet, sea-games)
├── docs/
│   ├── research/         ← Research docs, briefs, playbooks
│   └── handoffs/         ← Handoff docs, AAR files
├── media/
│   ├── design/           ← Design assets, SVGs, branding
│   └── archives/         ← Old/stale projects
├── WORKSPACE.md          ← This file
└── (dotfiles)            ← .bashrc, .config, etc. (hidden)
```

---

## 🚀 Quick Access

### Screenshots (Most Used!)
```bash
cd ~/screenshots
# Drop your screenshots here
ls -lh  # See all screenshots
```

### Claude's Projects
```bash
cd ~/projects/claude
ls  # MeniscusMaximus, PixelSports, CodeMonkeys, TradeGame, DrivingMeNuts, etc.
```

### Gemini's Projects
```bash
cd ~/projects/gemini
ls  # omnitender-repo, omnitender-web, omniverse, omnidesk, omni-herald, omnitender-worklog
```

### Shared/Fleet
```bash
cd ~/projects/shared
ls  # agent-corps, fleet, sea-games
```

### Fleet Blackboard (Critical)
```bash
cd ~/projects/shared/fleet
cat FLEET_PROTOCOL.md  # How the fleet works
```

### OmniTender Worklog (Gemini's Kanban)
```bash
cd ~/projects/gemini/omnitender-worklog
cat KANBAN.md  # Gemini's work queue
```

---

## 📊 What Goes Where

| Folder | Contains | Examples |
|--------|----------|----------|
| `~/screenshots/` | Player testing, UI feedback, bug reports | `volleyball-hud-fix.png`, `omnidesk-layout.jpg` |
| `~/projects/claude/` | Game dev, recovery app, tools | `PixelSports/`, `MeniscusMaximus/`, `CodeMonkeys/` |
| `~/projects/gemini/` | OmniTender ecosystem | `omnitender-web/`, `omniverse/`, `omnidesk/` |
| `~/projects/shared/` | Multi-agent infrastructure | `agent-corps/`, `fleet/` |
| `~/docs/research/` | Analysis, briefs, playbooks | `revenue-survey.md`, `game-design-docs/` |
| `~/docs/handoffs/` | Session handoffs, AAR files | `HANDOFF_2026-06-12.md` |
| `~/media/design/` | SVGs, logos, brand assets | `omnitender-logo.svg`, `brand-guidelines.md` |
| `~/media/archives/` | Old projects (reference only) | Stale repos, deprecated branches |

---

## 🔧 How to Use

### I need to test PixelSports
```bash
cd ~/projects/claude/PixelSports
npm run dev
```

### I need to check Gemini's work queue
```bash
cd ~/projects/gemini/omnitender-worklog
cat KANBAN.md
```

### I need to upload a screenshot for analysis
```bash
# Copy screenshot to:
cp ~/Downloads/my-screenshot.png ~/screenshots/
# Then tell Claude the filename
```

### I need to find a design doc
```bash
find ~/docs ~/media/design -name "*.md" -o -name "*.svg"
```

---

## 📝 Naming Convention

**Screenshots:** Use descriptive names
```
screenshots/
├── volleyball-hud-unreadable-before.png
├── volleyball-hud-fixed-after.png
├── omnidesk-dashboard-feedback.jpg
└── omniverse-sms-blocked-error.png
```

**Projects:** Keep repo names as-is (no renaming)
```
projects/claude/PixelSports/  ← matches GitHub repo name
projects/gemini/omnidesk/     ← matches GitHub repo name
```

---

## ✅ Checklist: Organized?

- [x] Screenshots folder exists and is top-level
- [x] Projects organized by owner (claude/gemini/shared)
- [x] Docs separated from code
- [x] Media (design, archives) separated
- [x] WORKSPACE.md created (you're reading it!)

---

## 🗑️ What About Old Stuff?

If a project becomes stale or archived:
```bash
mv ~/projects/claude/old-project ~/media/archives/old-project
```

Then update this document.

---

**Next:** Move key repos into their folders (optional, can do gradually).
