# Photo & likeness consent — M-12 standard (Tier B repos)

Repos that publish human imagery on public surfaces must document consent **before**
images ship. This file is the intake standard; pair it with `CONSENT_LOG.md` for
per-image records.

## Rules

1. **No undocumented minors' photos** on any public-surface path (website, gallery,
   README, social previews). COPPA treats a child's photo/video/voice as personal
   information requiring verifiable parental consent.
2. **Every real-person image** committed to a public path needs a matching row in
   `CONSENT_LOG.md` with status `DOCUMENTED` and a consent reference (WhatsApp reply,
   signed form scan, or ticket ID).
3. **Placeholder / stock / redacted images** use a `SAMPLE_` filename prefix OR a log
   row with status `SAMPLE` — never `DOCUMENTED` without real consent on file.
4. **Withdrawal:** when a parent/guardian revokes consent, mark the log row `WITHDRAWN`,
   remove the image from public surfaces promptly, and do not re-publish.

## Consent capture (practical)

- Use the repo's `docs/CONSENT_FORM.md` (or equivalent) for the permission text.
- Store evidence off-repo (secure drive / ops folder); the log records **that** evidence
  exists — not PII itself.
- For academies and youth programs: default to **no public gallery** until Simon/owner
  confirms documented parental consent for each athlete shown.

## CI / hook expectation

Tier B repos should enforce M-12 via git-guards filename-check (consent log entry or
`SAMPLE_` prefix). A checklist alone is not verification — owner/legal must confirm
consent is real.

**Audit date:** __DATE__  
**Owner:** deliberately unnamed
