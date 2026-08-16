# Wave A — Assessments queue tombstone — production deploy

**Verdict: PASS**  
**Stamp:** `20260801T033029Z`  
**Host:** `root@76.13.63.68`  
**Scope:** Explicit `GET /dashboard/prehire/assessments/queue` tombstone only (surgical insert into `app.py`)

## Production SHA

| Artifact | Value |
|----------|-------|
| `app.py` after deploy | `123b14961a6e3879f24d3d02d0b64febe77f5f4e924e9da318f5ea0c4f6bb7c6` |
| `app.py` before deploy | `2a7f1e8fe66ca3a0fdcfa6b3af95721252768aeb6177fbf4ed4d4eada71ebe2a` |
| Tombstone block | `4a13bc0912e6e8f753f411e998395fdf391942a262e6d4818ed92373346e8da7` |

Matches local qualified tombstone (`ops/evidence/assessments-queue-tombstone-waveA-local-20260801T032720Z`).

## Deploy method

Surgical insert of the tombstone route **immediately before**  
`@app.get("/dashboard/prehire/assessments/{attempt_id}")` — route ordering verified (`queue_before_attempt_id=true`).  
No Assessments UI, cohort logic, permissions, or other API changes.

## Gates

| Gate | Result |
|------|--------|
| Health after deploy | **200** |
| Orphan route HTTP status | **410 Gone** |
| Never 500 | **PASS** |
| `error=assessment_queue_route_removed` | **PASS** |
| Message points to `applications` + `overview_cohort` | **PASS** |
| AS02 re-gate (9 checks) | **PASS** |
| Cohort path `applications?overview_cohort=…` | **200** (2 apps) |
| Assessments list | **200** |
| Assessments config | **200** |
| Caller audit (dashboard src) | **0 hits** |
| Rollback → restore-new | **PASS** (SHA `2a7f…` → `123b…`) |
| Health after restore | **200** |

## Rollback

- Backup: `/opt/wathefni/backups/production-pre-assessments-queue-tombstone-20260801T033029Z`
- Scripts: `rollback/ROLLBACK.sh`, `rollback/RESTORE_NEW.sh`
- Exercise: rolled back to pre-deploy SHA, then restored tombstone SHA; health 200 both ways

## Evidence

- Local: `/Users/azizalmulla/Desktop/claw/ops/evidence/assessments-queue-tombstone-waveA-deploy-20260801T033029Z`
- Remote: `/opt/wathefni/production-evidence/assessments-queue-tombstone/20260801T033029Z`

## Final

**PASS**
