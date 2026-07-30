# Changelog

All notable changes to CodeMonkeys are documented here. Dates are merge dates
(UTC). Format follows [Keep a Changelog](https://keepachangelog.com/).

## 2026-07

### feat
- **feat:** config-backed feature-flag system for risky toggles (closes #182) (#213)
- **feat(desktop):** Linux packaging — build-linux.sh, .desktop entry, AppImage (#201)
- **feat:** add /healthz + /readyz probes (#174) (#198)
- **feat:** multi-admin — Owner promote/demote (#196)
- **feat:** startup config validation with fail-fast (#205)
- **feat:** request body size limit middleware (DoS guard) (#203)
- **feat:** expose OpenAPI docs at /api/docs /api/redoc (#214)
- **feat:** OpenAPI export script + docs smoke test (#172, partial) (#207)

### fix
- **fix(security):** encrypt mcp_config.json (OAuth client_secret) at rest [S4-B] (#216)
- **fix(ci):** repair broken YAML in ci.yml — main has been red (#217)
- **fix:** two test bugs failing on main (CI has been red) (#218)
- **test:** join background threads spawned during tests (fixes #212 CI flakiness) (#219)
- **fix(ci):** grant kanban-autolabel workflow write permissions (#210)
- **fix(ci):** reconcile desktop VERSION with NSIS installer (0.2.0 → 0.2.1) (#200)
- **fix:** monkey CLI defaults to hosted server, not localhost (#199)
- **fix:** CLI installer falls back through uv, not just pip (#197)
- **fix:** root-cause 'buttons do nothing' — script tags loaded before DOM (#186)
- **fix:** automate Docker static/ cache-bust instead of hand-edited comment (#187)

### ci
- **ci:** add pip-audit dependency vulnerability scan (#204)

### docs
- **docs:** operator runbook — deploy, rollback, incident triage (closes #181) (#208)
- **docs:** update STATE.md after #186/#187 merge + deploy (#188)
- **docs(forge):** FORGE_HYGIENE maintainer checklist + N-backlog status (#162)
- **docs(forge):** static surface map (#161)

### feat(m) — milestones
- **feat:** M-8 backup posture — restore drill + receipt (#165)
- **feat:** M-7 per-user attribution + message-content erasure (issue #70) (#164)
- **feat:** M-4 cloud-egress consent gate (issue #67) (#160)
- **feat:** S-3 hash-chained tamper-evident audit receipts (#159)

### security
- **security:** first audit report — 2 CRITICAL, 3 HIGH findings (#155)
- **fix(security):** remediate 2 CRITICAL + 3 HIGH audit findings (AUDIT-2026-06) (#156)
- **fix(security):** scope forwarded-allow-ips to Fly's private network (#157)

### cli + ui
- **cli:** add standalone terminal CLI (cli/) — Claude-Code/Cline-style REPL (#193)
- **cli:** add 'cm' short alias + fix Windows python.exe stub detection (#194)
- **feat(ui):** Jungle redesign — tab bar, slim left taskbar, jungle menu, theme CSS (#152)
- **feat(desktop):** bring native Windows/Linux desktop shell onto current main (#167)
- **feat(desktop):** CM-DESK-W2: Windows installer polish — NSIS, icon, build pipeline (#170)

### misc
- **feat:** launch CodeMonkeys $1/mo subscriptions (#191)
- **feat:** 12-to-4 ideation sweep (#148)
- **feat(forge):** docs-queue-sync — mark S5 notify-on-done shipped in wave registry (#185)
- **chore:** re-sync vendored corps doctrine from AgentCorps (issue #14) (#158, #168)
- **chore(deps):** bump cryptography from 48.0.0 to 48.0.1 (#153)
- **fix(ci):** CSP inline scripts + vertex project test (#163)

## 2026-06

### feat - waves 3-13 (security S1-S6, cost N1-N12)
- **feat:** Wave 3 (W11) - two-layer KB (rules + facts) with secret-leak guard (#30)
- **feat:** fly: wire /healthz (W1) as the http_service liveness check (#31)
- **feat:** Wave 4 #3 (phase 1) - fractal/tiered memory: deterministic theme-token digest (#33)
- **feat:** Wave 4 #5 - vendored Tailwind build pipeline (CDN still active) (#34)
- **feat:** Wave 4 #9 - connector marketplace: curated catalog + registry fallback (#35)
- **feat:** Wave 4 #5 - GitHub issue/webhook to PR runs (fail-closed, INERT until owner config) (#36)
- **feat:** Web terminal - Claude Code-style REPL fallback (red-teamed, double-gated, OFF by default) (#37)
- **feat:** Tailwind phase 2 - remove CDN script, tighten CSP script-src to self (#40)
- **feat:** Wave 7 (S2) - Fleet Deck read-only ops feed: GET /fleet-status.json (red-teamed) (#41)
- **fix:** duplicate-send bug (Nth message xN) + blank-base_url provider guard (#42)
- **feat:** Wave 9 (S3) - fractal memory phase 2: scrubbed tier-1 digest + cross-session pattern library (#43)
- **feat:** Wave 10 (S4 part A) - strip secret-named env vars from shell subprocesses (#44)
- **feat:** Wave 12 (S5) - notify-on-done: outbound run-completion ping (red-teamed) (#45)
- **feat:** Wave 13 (S6) - DESIGN: per-user isolation (no code; owner decision) (#46)
- **feat:** Single-tenant injection hardening - encrypt session_secret.key at rest + evict env secrets (#47)
- **feat:** Recovery - CM_MASTER_KEY_RESET break-glass + RECOVERY.md runbook (#48)
- **feat(N4):** unified diff preview for file mutations (#50)
- **feat(N2):** rolling daily spend cap across all sessions (#51)
- **feat(N1):** Smart provider failover with cooldown registry (#52)
- **feat(N3):** cost/usage dashboard (by-day, by-model, owner panel) (#53)
- **feat(N11):** owner-only audit-log viewer (GET /api/audit) (#54)
- **feat(N7):** Plan to Execute handoff (list specs + one-click execute) (#55)
- **feat(N9):** tool-error-repeat guard - nudge + abort on stuck loops (#59)
- **feat(N6):** session resume after server restart (#60)
- **feat(N5):** opt-in streaming for OpenAI-compatible model path (#62)
- **security:** pin starlette>=1.0.1 (CVE-2026-48710 auth bypass) (#57)
- **feat(S4-B):** encrypt model_config/mcp_tokens at rest + evict GITHUB_TOKEN (#58)
- **governance:** Phase 1 pilot: CM GOVERNANCE.md + git-guards + tier-A/B/D audit (#65)
- **feat(M-7):** real erasure cascade + tombstone + receipt (closes #66) (#69)
- **feat:** Layer A: free-model auto-lister (Model Deck) (#71, #74)
- **feat:** CodeMonkeys swarm visualizer (Phase 1) (#76)
- **feat(forge):** CM-W1 - N5 streaming output (#81); CM-W2 - N8 context auto-compaction (#82); CM-W3 - N12 model catalog refresh (#83)
- **feat(forge):** three-card Field Report triage + Docker fix (#84); CM-W4 - lint feedback loop (#85); Agents hub + hooks/skills (#86)
- **feat(forge):** CM-W6 - feedback triage list proposals + tests (#111); CM-W7 - S6 session ownership gates (#122)
- **feat(forge):** sync wave registry after session ownership merge (#147, #149, #150, #151); copy OTP secret + passkeys (#147)
- **docs:** N8 design doc - context auto-compaction (#63); N12 design doc - model catalog/pricing (#64)
- **frontend:** simplify Forge UI nav + terminal whitespace (#78); fix broken forge UI + PWA assets (#113)
- **chore:** gitignore .cursor/ + mark Wave 3 deployed (#32); Update rules/configs (#79); Add Cursor mission-command rule (#80)
- **docs:** Wave 5 consolidation - AAR refresh + suite verified green (#38); Wave 3 consolidation - RELEASE_NOTES + N1-N12 backlog (#56); Consolidation phase 2 - 535 green (#61)
