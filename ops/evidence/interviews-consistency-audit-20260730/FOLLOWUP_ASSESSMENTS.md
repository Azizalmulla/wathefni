# Follow-up correctness audit — Assessments

**Status:** AUDIT COMPLETE — awaiting contract approval (no implement)  
**Priority order:** 3 of 4 (Jobs → Candidates → Assessments → Ranking)  
**Audit report:** `ops/evidence/assessments-consistency-audit-20260730/REPORT.md`  
**Live proof:** `ops/evidence/assessments-consistency-audit-20260730/live-proof.json`  
**Date:** 2026-07-30

## Finding summary

**Verdict: FAIL** (cohort / attempt / scope contract)

- Three authorities: company-wide cohort application counts, attempt `status_counts` (every attempt), client page-local Needs review / Reports.
- In progress / Completed metrics fall back across unit boundaries (`peopleFor \|\| status_counts`).
- Live: `status_counts.expired=3` vs Resend cohort apps `=2` (superseded expired on multi-attempt app).
- Hybrid: cohort badges company-wide; opened lists assignment-scoped.
- Cancelled counted in Attempts totals but excluded from send cohorts; presentation maps cancelled → attention without SQL membership.
- Client `assessmentQueue` re-filters with stricter `cv?.received`.

## Proposed contract

See audit report §9: separate `assessments.cohort.*` vs `assessments.attempt.*` vs `assessments.review.*`; badge ≡ opened list ≡ same scope; no cross-fallback; cancelled Attempts-only.

## Not done

Implementation, UI redesign, deploy. Ranking untouched.
