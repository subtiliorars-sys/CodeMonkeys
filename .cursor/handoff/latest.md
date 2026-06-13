# Handoff — multi-project (2026-06-13, backed up + pushed)

## Cloud backups
- **Marketing library (6,641 emails):** `s3://subtiliorars-omnitender-web-380592535426/_private-backups/omniverse-marketing-20260613.tgz` (~102 MB)
- **Restore:** `cd ~/projects/gemini/omniverse && bash scripts/restore-marketing-s3.sh`

## Git pushed
| Repo | Branch | Notes |
|------|--------|-------|
| OmniVerse | `work/omniverse-email-fallback-monitor` | Gmail sync, digest, outreach |
| omnitender-web | `main` | Honest homepage + digest UI → triggers S3 deploy |
| MeniscusMaximus | `work/cairn-guided-experiences` | Cairn steps/experiences/dog (not master — deploy gate) |
| PixelSports | `work/store-launch-v0.1` | Broadside demo |

## Still local only (copy before switching laptops)
- `omniverse/.env` — Google OAuth client secret
- `omniverse/data/gmail-oauth.json` — refresh token (or set `GOOGLE_REFRESH_TOKEN` on Fly)

## Next
- Merge MM work branch → master when ready to deploy Cairn to Fly
- `fly deploy` OmniVerse branch when ready for Gmail sync on server
- Save refresh token in password manager
