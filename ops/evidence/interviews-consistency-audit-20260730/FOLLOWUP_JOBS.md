# Follow-up correctness audit — Jobs

**Status:** IMPLEMENTED + DEPLOYED — **PASS** (`20260730T150926Z`)  
**Priority order:** 1 of 4  
**Audit report:** `ops/evidence/jobs-consistency-audit-20260730/REPORT.md`  
**Implementation report:** `ops/evidence/jobs-queue-contract-20260730T150926Z/REPORT.md`  
**Date:** 2026-07-30

## Finding summary (pre-fix)

**Verdict was FAIL** (count / View-candidates contract)

- Applications badge + funnel = historical total (`application_count`, all statuses including hired/rejected).
- View candidates = `role_active` (excludes hired/rejected/**withdrawn**).
- Close confirm = `active_count` (excludes hired/rejected only — still counts withdrawn).
- Live proof: `IT_MAINTENANCE` / `MARKETING_SPECIALIST` badge 1 → View candidates 0; `SOCIAL_MEDIA_MANAGER` badge 2 → View candidates 1.
- Job status aliases: UI `published`→Open vs backend →Closed; filter is exact DB status only.

## Shipped contract

See implementation report. Badge / close / View candidates share `jobs.active_pipeline` (excludes hired, rejected, withdrawn, archived). Funnel retains historical statuses. Status aliases shared via `jobs_queue_contract.py`.

Live proof after deploy: IT 0=0, Marketing 0=0, Social 1=1 — **PASS**.

## Not done

Candidates / Assessments / Ranking follow-ups beyond Jobs wiring.