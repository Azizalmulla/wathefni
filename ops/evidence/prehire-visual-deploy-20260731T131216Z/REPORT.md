# Pre-hiring visual + mobile nav — production deploy

**Stamp:** `20260731T131216Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  
**Scope:** Pre-hire visual unification + mobile PRE-HIRING active-route nav (dashboard static only)  
**Backend / orchestrator:** unchanged this deploy  
**M365 mail / hybrid email:** already live from prior packs (not redeployed here)

---

## Verdict

| Gate | Result |
|---|---|
| Health before | **200** |
| Dashboard before | **200** |
| Dist rsync to `/var/www/wathefni-dashboard` | **PASS** |
| Live chunk | `dashboard--cPiPiYu.js` |
| Marker proof (mobile chip/rail/more) | **PASS** (`remote/markers.json`) |
| Health after | **200** |
| Dashboard after | **200** |
| Deploy performed | **YES** |

**Overall: PASS — LIVE**

---

## Backup / rollback

- Backup: `/opt/wathefni/backups/production-pre-prehire-visual-20260731T131216Z/`
- Rollback: `ROLLBACK.sh` in that backup (also copied to this pack)
- Live snapshot / restore-new: evidence `dashboard-dist-live/` + `RESTORE_NEW.sh` on backup path

Remote evidence: `/opt/wathefni/production-evidence/prehire-visual/20260731T131216Z/`

Prior qual packs:
- `ops/evidence/prehire-mobile-nav-final-20260731T124927Z/`
- `ops/evidence/prehire-visual-fix-20260731T023139Z/`
- Waivers accepted as documented there

---

## Notes

- Dashboard-only ship. Orchestrator service was not restarted.
- Caddy reloaded after static publish.
- Unrelated Vitest waivers remain accepted; not part of this deploy surface.
