# Handoff — CodeMonkeys mobile + feedback (2026-06-13)

**Owner intent:** Phone-usable CodeMonkeys console; anonymous feedback (especially login issues); no floating pills cluttering login on CM or MM.

---

## CodeMonkeys (`projects/claude/CodeMonkeys/`)

**Branch:** `work/frontend-polish` (local, uncommitted)

### Shipped (local)

| Feature | Files |
|---------|--------|
| Mobile drawer console (≤767px) | `static/forge/index.html`, `app.js`, `workbench.js` |
| PWA install | `manifest.webmanifest`, `/sw.js` route, `icons/icon-{192,512}.png` |
| Push on approval gates | `push.js`, `server.py` `/api/push/*`, `pywebpush==2.0.1` |
| Mobile lite `/m` | `server.py` route, `cm-lite` CSS in `index.html` |
| Anonymous feedback | `feedback.js` + `server.py` `optional_verify_user` |
| **No 💬 on login/setup** | `feedback.js` CSS + `app.js` `syncWithAuthScreen()` |

### Deploy CM

```bash
cd ~/projects/claude/CodeMonkeys
git add requirements.txt server.py static/forge/   # stage only CM paths
# commit + push work/frontend-polish → Fly deploy per your CM pipeline
```

### Verify CM (after deploy)

- Phone ≤767px: ☰ drawer, chat composer, `/m` lite route
- Settings → 🔔 Approval push (HTTPS required)
- Login screen: **no** floating 💬; after login 💬 returns
- Login → anonymous feedback works from main console (not from login — by design)

---

## Meniscus Maximus (`projects/claude/MeniscusMaximus/`)

**Branch:** `work/cairn-guided-experiences` (local, uncommitted; **includes other WIP** — dog assets, home, etc.)

### Shipped (this thread — feedback/mobile overlap)

| Feature | Files |
|---------|--------|
| Anonymous `/api/feedback` (no token) | `server.py`, `test_crisis_surfaces.py`, `test_feedback_screenshot.py` |
| Steady Ground vs 💬 overlap fix | `static/console/feedback.js`, `index.html` mobile CSS |
| **No 💬 on login/recovery** | `static/console/app.js`, `feedback.js` CSS `:has()` |
| Cairn parity (anonymous submit) | `static/cairn/feedback.js`, `field-report.js` |

**Steady Ground** (`🫂` pill, bottom-left on mobile) **stays on login** — crisis exit is intentional.

### Deploy MM

```bash
cd ~/projects/claude/MeniscusMaximus
# Prefer a focused commit: server.py + static/console/feedback.js field-report.js index.html app.js + tests
# Branch has unrelated changes — do NOT git add -A from home root
fly deploy   # master → Fly (per repo rules)
```

### Verify MM (after deploy)

- Login: only **Steady Ground** (bottom-left on phone), no 💬
- After sign-in: 💬 bottom-right; modal hides both pills while open
- Anonymous report from Settings → Send Feedback or 💬 (no “Please sign in first”)
- `python3 test_crisis_surfaces.py` && `python3 test_feedback_screenshot.py` (pass locally)

---

## Cross-app confusion (for next agent)

- User voice-to-text **“Study Ground”** = **Steady Ground** (MM crisis button only)
- CodeMonkeys has **no** Steady Ground — only 💬 feedback FAB
- Earlier CM feedback fixes were correct repo; MM needed separate pass

---

## Not done / optional next

- CM: commit + Fly deploy not run this session
- MM: commit + deploy not run; branch mixed with dog/companion WIP
- PWA “Add to Home Screen” smoke test on real Android
- Push notifications end-to-end test on HTTPS Fly URL
- Login-screen “Report a problem” link (if feedback off login is too hidden)

---

## Key paths

| What | Path |
|------|------|
| CM mobile CSS/JS | `CodeMonkeys/static/forge/{index.html,app.js,feedback.js,push.js,sw.js}` |
| CM push API | `CodeMonkeys/server.py` (~`/api/push/*`, `request_approval`) |
| MM console feedback | `MeniscusMaximus/static/console/{feedback.js,field-report.js,app.js}` |
| MM Steady Ground markup | `MeniscusMaximus/static/console/index.html` (~L317) |

**Transcript:** `.cursor/projects/home-subtiliorars/agent-transcripts/0d0a50e5-adbb-420d-8a70-24368a482995/`
