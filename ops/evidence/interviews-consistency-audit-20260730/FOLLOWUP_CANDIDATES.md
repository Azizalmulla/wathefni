# Follow-up correctness audit — Candidates

**Status:** IMPLEMENTED + DEPLOYED — **PASS** (`20260730T160407Z`)  
**Priority order:** 2 of 4 (Jobs → Candidates → Assessments → Ranking)  
**Audit report:** `ops/evidence/candidates-consistency-audit-20260730/REPORT.md`  
**Implementation report:** `ops/evidence/candidates-stage-contract-20260730T160407Z/REPORT.md`  
**Date:** 2026-07-30

## Finding summary (pre-fix)

**Verdict was FAIL** (stage display / filter contract)

- Stage badge forced Talent Pool → New while New filter excluded `needs_role` / `import_review`.
- Offer was display-only; lifecycle mapped offer → shortlisted.
- List `total` already aligned with opened Stage filter SQL.

## Shipped contract

- View axis owns Talent Pool / no job; Stage column shows quiet `—` for held Talent Pool.
- Stage buckets share one contract for display + filter expand (incl. `offered`/`offer_sent` → Shortlisted).
- Unknown statuses → Unknown, not New.

Live proof: 2 Talent Pool rows not New; New filter = early lifecycle only; offer aliases Shortlisted — **PASS**.

## Not done

Assessments / Ranking follow-ups. Visual redesign. First-class Offer lifecycle stage.
