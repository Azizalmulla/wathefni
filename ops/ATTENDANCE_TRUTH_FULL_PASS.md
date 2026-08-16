# ATTENDANCE_TRUTH_FULL_PASS

**Status:** ACCEPTED by owner 2026-08-11 — C1 remains **FROZEN** (do not reopen for C2+)  
**Date:** 2026-08-11  
**Evidence:** `ops/evidence/attendance-truth-c1-20260811T193251Z`  
**Charter:** `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`  
**Freeze amendment:** `ops/ATTENDANCE_TRUTH_C1_FREEZE_AMENDMENT.md`  
**Qualify:** `ops/qualify-attendance-truth-c1-staging.sh`

## Proven

1. Global `CAPTURE_INGEST` off denies ingest  
2. Empty company allowlist denies (fail closed)  
3. Company-entitled ingest → append-only punches → day projection  
4. Exception/correction: approve ≠ apply; apply mutates projection version  
5. Reject does not apply  
6. Prior attendance freeze regression remains green  

## Posture

- Canary pattern: WATHEFNI or dedicated workforce-truth tenant only — **no broad enable**  
- Production systemd: global ingest remains **OFF**  
- Synthetic-only authority/ops posture preserved for production; C1 prove uses labeled synthetic subjects  
- Assistant mutations: **OUT** of Wave 2 MVP  

## Stop

Owner accepted. C1 remains frozen. C2 Leave Enforcement proceeded under charter §15.
