# Attendance Truth C1 — Freeze Amendment

**Status:** AMENDS `ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` for Wave 2 **C1 only**  
**Charter:** `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED` (2026-08-11)  
**Pass stamp:** `ATTENDANCE_TRUTH_FULL_PASS`  
**Qualify:** `ops/qualify-attendance-truth-c1-staging.sh`

## What changes

| Prior freeze | C1 amendment |
|---|---|
| `CAPTURE_INGEST` must stay off | **Global** `WATHEFNI_ATTENDANCE_CAPTURE_INGEST` remains **off** in production systemd. Company-entitled ingest requires process/canary: ingest **on** ∧ non-empty `WATHEFNI_ATTENDANCE_CAPTURE_INGEST_COMPANIES` (empty = nobody). |
| No company ingest allowlist | Added fail-closed allowlist via `attendance_truth_c1.py` |
| Real device ingest banned without owner wave | This document **is** the owner-approved C1 wave for company-scoped entitled ingest prove |

## What does **not** change

1. Punch immutability — corrections create new projection versions only  
2. Approve ≠ apply; dual approval where configured  
3. Manager self-denial + scope checks  
4. Payroll money impact remains **NO-GO**  
5. `AUTHORITY_SYNTHETIC_ONLY` / `OPS_SYNTHETIC_ONLY` production posture unchanged by this amendment (C1 prove uses labeled synthetic subjects)  
6. QR / GPS / kiosk remain off  
7. No broad enable beyond WATHEFNI / dedicated workforce-truth tenant  
8. Assistant mutations remain **OUT** of Wave 2 MVP  

## Rollback

```text
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
Clear WATHEFNI_ATTENDANCE_CAPTURE_INGEST_COMPANIES / WATHEFNI_ATTENDANCE_TRUTH_COMPANIES
WATHEFNI_ATTENDANCE_TRUTH_C1=off
```

Do not DROP attendance tables.

## Next

Stop for owner review. **Do not start C2** until `ATTENDANCE_TRUTH_FULL_PASS` is accepted.
