# Follow-up correctness audit — Ranking (not in this change)

**Status:** OPEN — recorded from Interviews consistency audit 20260730  
**Priority order:** 4 of 4 (Jobs → Candidates → Assessments → Ranking)  
**Do not mix into Interviews queue contract deploy.**

## Finding summary

**Verdict: MISMATCH**

- Header “matching” count uses full non-terminal pool (`total_matching` / `pool_total`).
- `eligible_count` is returned but not used as the headline badge.
- List is top-N of that pool; eligibility is row chrome only.

## Suggested audit scope (later)

1. Decide whether headline means pool size or eligible-only.
2. Align copy, badge, and list filter to one predicate.
3. Contract tests + separate deploy.

## Source pointers

- `apps/wathefni-dashboard/src/pages/RankingPage.tsx`
- `wathefni-orchestrator/candidate_ranking.py`
- `ops/evidence/interviews-consistency-audit-20260730/REPORT.md`
