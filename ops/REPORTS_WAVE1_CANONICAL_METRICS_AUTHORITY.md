# Reports Wave 1 — Canonical Metrics Authority

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T105106Z`  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Scope:** One backend-authoritative metrics contract for Reports cards, breakdowns, and analytics  
**Not in this wave:** page redesign, export changes, colors, unrelated pages

---

## Final verdict

**PASS — Wave 1**

Every Reports metric now carries explicit `key`, `label`, `value`, `unit`, `current_or_history`, `source_authority`, and `export_key`. Open roles, current stage breakdown, assessment attempts, current follow-ups, and delivery-failure history are all derived from one backend contract and consumed by cards/breakdowns without independent frontend counting. The four audit mismatches are fixed.

---

## Product rules locked

| Rule | Metric |
|---|---|
| Main Role metric = currently open roles | `open_roles` (unit `role`, current) |
| Role export = all roles with status | export path (`role_export_total` metadata) |
| Main Follow-up metric/export = current open follow-up applications | `followups_current` (unit `application`, current) |
| Delivery failure history = separate historical export | `delivery_failure_history` (unit `event`, history) |
| Stage breakdown = current canonical application stage | `applications_by_stage` |
| Assessment metrics = attempts | `assessment_pending` / `assessment_completed` / `assessment_expired` (unit `attempt`) |
| Interview metrics = interviews | `interviews` (unit `interview`) |

## Contract

`reports.metrics` (`reports_metrics_v1`):

- `metrics[]`: key, label, value, unit, current_or_history, source_authority, export_key
- `breakdowns { applications_by_stage, assessment_status, interview_status }`
- `role_export_total`

## Fixed mismatches

| Before | After |
|---|---|
| Role card 0 vs 11 exported roles | `open_roles = 8` (currently open roles) + `role_export_total = 19` (all roles with status) |
| Ready for review 2 vs stage breakdown 0 | `ready_for_review = 2`; stage breakdown now uses **current application stage** (matches application truth) |
| Assessment 0/0 vs real attempts | pending 1 / completed 1 / expired 3 (attempt unit) |
| Follow-up 21 historical events vs 2 current applications | `followups_current = 2` (applications) + `delivery_failure_history = 21` (events, labeled history) |

---

## Live proof (`20260728T105106Z`)

| Assertion | Result |
|---|---|
| Open role count correct | **8 = 8** |
| Current stage breakdown matches application truth | **PASS** |
| Assessment counts match attempts | **PASS** |
| Current follow-ups match actionable applications | **2 = 2** |
| Delivery failure history separately identified | **21 events (history)** |
| All units explicit | **PASS** |
| Health 200 | **PASS** |
| Rollback / restore | **PASS** |
| No unrelated mutations | **PASS** |

Evidence: `/opt/wathefni/production-evidence/reports-wave1-canonical-metrics/20260728T105106Z/live-proof.json`

---

## Rollback / restore

| Step | Result |
|---|---|
| Backend rollback (`app.py`) | Health **200** |
| Dashboard rollback → previous asset | Health **200** |
| Backend restore (+ `reports_metrics.py`) | Health **200**; proof PASS |
| Dashboard restore | Health **200**; asset `dashboard-B4K0GysF.js` |

---

## Remaining limitations

- Exports themselves are unchanged in this wave (raw labels in exports are a later wave).
- Role metric uses positions marked open/active/published; role export includes all roles with status.
- Follow-up export still points to the follow-ups export type; a dedicated delivery-history export type is a follow-up wave.
- Stage breakdown uses current application status strings (canonical stage labeling is a presentation wave).

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Canonical metrics contract returned | **PASS** |
| Open roles correct | **PASS** |
| Stage breakdown = current application stage | **PASS** |
| Assessment metrics = attempts | **PASS** |
| Interview metrics = interviews | **PASS** |
| Follow-ups current vs delivery history separate | **PASS** |
| Cards/breakdowns consume contract | **PASS** |
| Tenant/permission boundaries | **PASS** |
| EN/AR + RTL + direct links | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated mutations | **PASS** |

**Stop after Wave 1.**
