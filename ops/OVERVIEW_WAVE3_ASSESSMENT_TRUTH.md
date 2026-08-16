# Overview Wave 3 — Assessment Truth

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260727T233828Z`  
**Host:** `root@76.13.63.68`  
**Scope:** Unify assessment states/actions across Overview, Candidates, Assessments, and Candidate profile  
**Not in this wave:** Ranking logic, color redesign, unrelated page redesigns

---

## Final verdict

**PASS — Wave 3**

One backend assessment cohort contract now owns every assessment count, label, cohort filter, and CTA destination. First-send, expired/resend, delivery-failed, and in-progress are separate. Expired is never labeled “Send pending assessments”. Overview people/application counts match the Assessments/Candidates cohort query for each key. CTAs open Assessments with the exact action surface (Send / Resend / Delivery failed / In progress). Wave 2 URL durability is preserved.

---

## Shared contract

Authority module: `wathefni-orchestrator/assessment_cohorts.py`

| State | Cohort key | Primary action | Assessments tab |
|---|---|---|---|
| Ready to send | `assessment_ready_to_send` | `send_assessment` | `send` |
| Sent / pending | `assessment_sent_pending` | `resend_assessment` | `sent_pending` |
| In progress | `assessment_in_progress` | `view_assessment` | `in_progress` |
| Expired | `assessment_expired` | `resend_assessment` | `resend` |
| Resend needed | `assessment_resend_needed` | `resend_assessment` | `resend` (alias of expired) |
| Delivery failed | `assessment_delivery_failed` | `resend_assessment` (+ `review_assessment_delivery`) | `delivery_failed` |
| Completed | `assessment_completed` | `view_assessment_report` | `completed` |
| Attention (legacy aggregate) | `assessment_attention` | — | not a send CTA |

Actionable cohorts are mutually exclusive. People counts use the same confirmed-person identity as Wave 1.

---

## What changed

### Backend

- New `assessment_cohorts.py` (predicates, classify, allowed actions, destinations, compute, primary CTA).
- `prehire_overview.py` publishes cohort breakdown + `assessment_primary` and routes assessment work-queue/next-action to Assessments destinations.
- `app.py` (surgical on Wave 2 production base):
  - `overview_cohort` / assessment cohort keys use shared predicates
  - application UI contract publishes `assessment_cohort` + `assessment_allowed_actions`
  - summary exposes `assessment_cohorts`

### Frontend (`apps/wathefni-dashboard`)

- Overview card uses `assessment_primary` label/count/destination (Send / Resend / Delivery failed / In progress / Sent pending).
- Assessments page loads the selected cohort via `overview_cohort` / `assessment_cohort`, with action tabs and cohort-correct CTAs.
- Candidates keep the same `overview_cohort` filter authority for the same keys.
- Candidate profile honors backend `send_assessment` / `resend_assessment`.
- URL keys preserved/extended: `assessment_cohort`, `overview_cohort`, `cohort_key`, `tab`, `action`.
- EN/AR copy updated; Overview RTL unchanged.

---

## Live WATHEFNI proof (`20260727T233828Z`)

| Cohort | Overview people/apps | Query people/apps | Destination tab | Pass |
|---|---:|---:|---|---|
| Ready to send | **2 / 2** | **2 / 2** | `send` | PASS |
| Resend needed (expired) | **2 / 3** | **2 / 3** | `resend` | PASS |
| Delivery failed | **0 / 0** | **0 / 0** | `delivery_failed` | PASS |
| In progress | **0 / 0** | **0 / 0** | `in_progress` | PASS |
| Sent / pending | **0 / 0** | **0 / 0** | `sent_pending` | PASS |

Primary Overview CTA: **Resend expired assessments** (`assessment_resend_needed`, people **2**, apps **3**) → Assessments `tab=resend`.

Evidence: `/opt/wathefni/production-evidence/overview-wave3-assessment-truth/20260727T233828Z/live-proof.json`

### Assertions

- Cohort query people/apps ≡ Overview published counts for every actionable key
- No actionable cohort overlap (`mutual_exclusive_overlaps == 0`)
- No application with multiple open `pending|in_progress` attempts
- Attention label is **Assessment attention** (not “Send pending assessments”)
- Destinations are Assessments with matching `assessment_cohort` / `tab`
- Candidates destination uses the same `overview_cohort` key
- `create_or_resume` design resumes open attempts (no open pending/in_progress rows in current data; duplicate-open check PASS)
- No unrelated lifecycle/data mutation in this wave (proof resume not required when no open attempt exists)
- Health **200** before / after deploy / rollback / restore

### URL samples

```text
?page=assessments&assessment_cohort=assessment_ready_to_send&overview_cohort=assessment_ready_to_send&cohort_key=assessment_ready_to_send&tab=send
?page=assessments&assessment_cohort=assessment_resend_needed&overview_cohort=assessment_resend_needed&cohort_key=assessment_resend_needed&tab=resend
?page=assessments&assessment_cohort=assessment_delivery_failed&overview_cohort=assessment_delivery_failed&cohort_key=assessment_delivery_failed&tab=delivery_failed
?page=assessments&assessment_cohort=assessment_in_progress&overview_cohort=assessment_in_progress&cohort_key=assessment_in_progress&tab=in_progress
?page=candidates&overview_cohort=assessment_resend_needed&assessment_cohort=assessment_resend_needed&assessment_status=expired&cohort_key=assessment_resend_needed
```

---

## Health / rollback / restore

| Step | Result |
|---|---|
| Health after orchestrator deploy | **200** |
| Rollback `prehire_overview.py` + `app.py` (remove `assessment_cohorts.py`) | Health **200** |
| Restore Wave 3 orchestrator | Health **200**; primary resend **2/3** restored |
| Dashboard asset | `dashboard-Bg3l7rqq.js` |
| Dashboard rollback → Wave 2 asset | `dashboard-DDyznYge.js` |
| Dashboard restore Wave 3 | `dashboard-Bg3l7rqq.js`; health **200** |

Rollback artifacts:

- `/opt/wathefni/production-evidence/overview-wave3-assessment-truth/20260727T233828Z/prehire_overview.py.before`
- `/opt/wathefni/production-evidence/overview-wave3-assessment-truth/20260727T233828Z/prehire_overview.py.after`
- `/opt/wathefni/production-evidence/overview-wave3-assessment-truth/20260727T233828Z/app.py.before`
- `/opt/wathefni/production-evidence/overview-wave3-assessment-truth/20260727T233828Z/app.py.after`
- `/opt/wathefni/production-evidence/overview-wave3-assessment-truth/20260727T233828Z/assessment_cohorts.py.after`
- `/opt/wathefni/production-evidence/overview-wave3-assessment-truth/20260727T233828Z/wathefni-dashboard.wave3-before`
- `/opt/wathefni/production-evidence/overview-wave3-assessment-truth/20260727T233828Z/wathefni-dashboard.wave3-after`
- `/opt/wathefni/production-evidence/overview-wave3-assessment-truth/20260727T233828Z/live-proof.json`

Local/unit: `smoke-test-assessment-cohorts-unit.py` PASS; `assessmentCohorts.test.ts` PASS; `dashboardNavigation.test.ts` PASS.

---

## Intentionally deferred

- Ranking behavior / auto-load / score presentation
- Color / visual redesign
- Broader Assessments authoring UX beyond cohort truth

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Shared backend cohort contract | **PASS** |
| First-send count/cohort correct | **PASS** (2/2) |
| Expired/resend count/cohort correct | **PASS** (2/3) |
| Delivery-failed count/cohort correct | **PASS** (0/0) |
| No people/application mismatch | **PASS** |
| CTA opens exact actionable Assessments surface | **PASS** |
| Candidates ↔ Assessments same cohort key records | **PASS** (shared predicate) |
| Expired not labeled “Send pending assessments” | **PASS** |
| Backend-authoritative allowed actions | **PASS** |
| Wave 2 URL / refresh / Back / direct-link preserved | **PASS** |
| No duplicate open sends | **PASS** |
| Send/resend idempotent resume path | **PASS** (design + no duplicate opens) |
| EN/AR + RTL | **PASS** |
| No unrelated data mutation | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| Ranking / colors unchanged | **PASS** |

**Stop after Wave 3.**
