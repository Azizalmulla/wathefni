# Performance Reviews C2 — Freeze Amendment

**Stamp:** `PERFORMANCE_REVIEWS_FULL_PASS`  
**Charter:** `WAVE4_PERFORMANCE_TALENT_CHARTER: APPROVED` (§0.8.3–0.8.4)  
**Module:** `wathefni-orchestrator/performance_reviews_c2.py`  
**Prior:** C1 `PERFORMANCE_GOALS_FULL_PASS` ACCEPTED / frozen

## What this slice owns

- Review cycle authority: draft → configured → launched/in_progress → calibration_ready → closed  
- Launch snapshot of template/scale/competency/weights/assignments/population/visibility/anonymity/dues  
- Separate self / manager / 360 / final rating layers  
- Optional C1 goal evidence snapshot contract  
- Real 360 anonymity with minimum-response fail-closed  
- Versioned rating scales; custom labeled scales  
- Reviewer reassignment with audit  
- Submitted immutability + explicit amendment reopen (not silent)

## What this slice does **not** own

- Calibration mutations (C4) — C2 may set final from manager on close without erasing layers  
- Check-ins / competency product depth (C3)  
- Talent / HiPo / potential / 9-box  
- Assistant mutations  

## Rollback

```text
WATHEFNI_PERFORMANCE_REVIEWS_C2=off
Clear WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES
WATHEFNI_PERFORMANCE_KILL=on (optional)
Disable company entitlement — historical reviews preserved
```

## Next

C2 frozen and owner-accepted 2026-08-12. C3 may proceed; do not reopen C1/C2.
