# Reports Wave 2 — Canonical Exports & Human-Readable Labels

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T111003Z`  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Preserved:** Reports Wave 1 metrics authority, permissions, tenant boundaries, EN/AR, RTL

---

## Final verdict

**PASS — Wave 2**

Every export now uses the same canonical authorities as the Reports metrics, human-readable labels only, and an explicit unit + current/history meaning. Current follow-ups no longer export 21 historical events (now **2 current applications**); delivery-failure history remains available as a separate export (**21 events**). No raw internal status keys appear in leadership exports.

---

## Export contract

| Export | Unit | Current/History | Notes |
|---|---|---|---|
| Candidate report | application | current | canonical current stage, human labels |
| Role report | role | current | all roles with **Open/Closed** status |
| Assessment report | attempt | current | assessment presentation/report authority states |
| Interview report | interview | current | `interview_presentation_v1` + canonical review labels |
| Follow-up report | application | **current** | current open follow-up applications only |
| Delivery failure history | event | **history** | historical failed delivery events |

Each export declares its unit and current/history meaning via `EXPORT_UNITS`. Null stays blank, never zero.

## Labels (no raw keys)

- `screening_complete` / `review_pending` → **Ready for review**
- `needs_review` → **Needs review**
- `notes_pending` → **Review pending**
- `feedback_complete` → **Reviewed**
- Role status → **Open / Closed**
- Assessment attempt → **Sent / In progress / Expired / Completed / Cancelled**
- Interview → **Scheduled / Rescheduled / Completed / No-show / Cancelled**

---

## Fixed issues

| Before | After |
|---|---|
| Follow-up export = 21 historical events | Follow-up export = **2 current applications** |
| Delivery history mixed into follow-up | Separate `followup_delivery_history` export = **21 events** |
| Raw `screening_complete` / `needs_review` / `feedback_complete` | Human labels across all exports |
| Role card vs export confusion | Role export lists **all roles with Open/Closed**; card keeps currently open roles (Wave 1) |

---

## Proof (`20260728T111003Z`)

| Assertion | Result |
|---|---|
| Card/export parity where same scope | **PASS** (follow-ups 2 = 2; assessment/interview rows match attempts/interviews) |
| Current follow-ups ≠ 21 historical events | **PASS** (2 current) |
| Delivery history available separately | **PASS** (21 events) |
| All status labels human-readable | **PASS** (no raw keys in any export) |
| Canonical assessment/interview truth used | **PASS** |
| Role export = all roles with Open/Closed | **PASS** (11 roles) |
| Null stays blank | **PASS** |
| Health 200 | **PASS** |
| Rollback / restore | **PASS** |
| No unrelated mutations | **PASS** |

Evidence: `/opt/wathefni/production-evidence/reports-wave2-canonical-exports/20260728T111003Z/live-proof.json`

---

## Rollback / restore

| Step | Result |
|---|---|
| Backend rollback (`reports_v1.py`) | Health **200** |
| Backend restore | Health **200**; proof PASS |

---

## Remaining limitations

- The Reports page UI has not been redesigned (Wave 1/2 are authority + exports only).
- Delivery-failure history export keeps technical channel/provider values (`octopus`, `no_usable_conversation_id`) as history detail; these can be humanized in a presentation wave if leadership needs friendlier history.
- Role card (open roles) and role export (all roles) intentionally represent different scopes; both are now labeled.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Canonical export contract (unit + current/history) | **PASS** |
| Human-readable labels only | **PASS** |
| Current-state exports separate from history | **PASS** |
| Counts match metadata where same scope | **PASS** |
| No raw internal status keys | **PASS** |
| Canonical assessment/interview authorities used | **PASS** |
| Permissions/tenant/EN/AR/RTL | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated mutations | **PASS** |

**Stop after Wave 2.**
