# Pre-hire semantic composition — production deploy

**Stamp:** `20260731T190529Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  
**Scope:** Dashboard static only (composition pastels + neutral Assistant chips)  
**Prior local pack:** `ops/evidence/prehire-semantic-composition-20260731T185921Z/`  
**Backend / orchestrator:** unchanged

---

## Verdict

| Gate | Result |
|---|---|
| Health before | **200** |
| Dashboard before | **200** |
| Dist rsync | **PASS** |
| Live chunk | `dashboard-CgDXvZTr.js` (was `dashboard-CsYb-K_I.js`) |
| Composition markers | **PASS** (jobs/interview tiles, candidates people band, soft CSS, neutral Assistant chips) |
| Health after | **200** |
| Dashboard after | **200** |
| Deployed | **YES** |

**Overall: PASS — LIVE**

---

## What shipped

- Larger pastel composition surfaces (Jobs / Interviews / Candidates / Assessments / Ranking / Reports / Calendar)
- Assistant suggestion chips reverted to neutral cream
- Soft semantic token washes saturated toward Overview/mobile

## Backup / rollback

- Backup: `/opt/wathefni/backups/production-pre-semantic-composition-20260731T190529Z/`
- Rollback: `ROLLBACK.sh` in that backup (copied to this pack)
- Live snapshot: remote evidence `dashboard-dist-live/`

Remote evidence: `/opt/wathefni/production-evidence/prehire-semantic-composition/20260731T190529Z/`
