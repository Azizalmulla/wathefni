# Auth Wave 2 Phase 5 — Basic device security

**Stamp:** `20260807T045603Z`  
**Verdict:** **partially proven** (routes live + unit + OTA shipped; physical Aziz/Talal matrix pending)  
**Contract:** `ops/AUTH_WAVE2_PHASE5_DEVICE_SECURITY_CONTRACT.md`  
**Do not begin Phase 6.**

## Shipped

| Surface | What |
|---|---|
| Backend | `GET /app/device-security` · activate `platform` + `replaced_previous_device` · HR `GET/POST .../app-access` · revoke clears refresh hashes |
| Employee mobile | Settings → Device security · Sign out this device · one-time new-device notice |
| HR dashboard | Compact **App access** card (status / device / last active / Revoke / Re-invite) |
| Canary OTA | `4cb17ad8-2fea-4f19-954d-95a418ec265d` |

## Prove

- Phase 5 unit: **31/24** → 31/31 (`prove/unit.txt`)
- Live: `/app/device-security` → **401** (not 404) on public edge
- Live: `/dashboard/.../app-access` → **401** (not 404)
- Orchestrator backup: `/opt/wathefni/backups/production-pre-auth-wave2-phase5-20260807T045603Z`

## Owner / canary matrix (pending)

Aziz `WATHEFNI-96599338566` · Talal `WATHEFNI-96550252254`

1. Settings → Device security shows platform, activated, last active, Active  
2. Sign out this device → local clear → activation  
3. HR revoke → old PIN/Face ID cannot restore access  
4. New-phone activate → old phone returns to activation · notice once · PIN + Face ID setup  
5. Airplane mode / 5xx does not revoke  
6. Bank ESS / onboarding / payroll / nav unchanged · EN/AR/RTL  

## Rollback

1. Restore `/opt/wathefni/orchestrator/app.py` from backup above · `systemctl restart wathefni-orchestrator`  
2. Restore dashboard tarball from same backup if needed  
3. Republish prior canary OTA (`1f0fcfdb-…` Forgot PIN confirm / `af0c0998-…` Phase 4)

## Remaining risks

- Sessions activated before Phase 5 may show platform **unknown** until re-activate  
- Physical new-device / HR revoke matrix not yet owner-stamped  
- Wave1 freeze unit still flags `expo-local-authentication` (Phase 2+; pre-existing)
