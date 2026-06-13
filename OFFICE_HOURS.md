# CodeMonkeys — Office hours

**Cloud worker:** every 2h, 9–5 weekdays (cron offset :10).  
**Verify:** `pytest` (matches CI)  
**Playtest:** Forge UI at `/forge` when UI waves land

## 5-min PR checklist
1. CI **CI** workflow green  
2. One wave scope only (`WAVES.md`)  
3. No `server.py` auth weakening or secret leakage  
4. Merge same day → next wave auto-picks up  

Sensitive (manual merge): `SECURITY.md`, `server.py`, `fly.toml`, `GOVERNANCE.md`.
