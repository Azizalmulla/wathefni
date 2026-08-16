# Reports Wave 4 — Final Truth & Export Cleanup

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T191018Z`  
**Host:** `root@76.13.63.68`  
**Company:** WATHEFNI  
**Preserved:** Waves 1–3, canonical lifecycle/assessment/interview/permission authorities. No unrelated page changes.

---

## Final verdict

**PASS — Wave 4**

Stage breakdown now merges backend stages into one HR-facing label per state (“Ready for review” appears **once** with the merged count **3**). Applications by role is populated from canonical current application data. The export is named **Candidate applications** (application unit; people count remains secondary metadata). Delivery-failure history stays a separate historical/admin export and now shows only safe human-readable issues — no raw backend keys, provider URLs, OAuth errors, tokens, stack traces, or internal IDs.

---

## Fixed defects

| Defect | Fix |
|---|---|
| Duplicate stage labels | Merged via canonical stage map; one row per HR label |
| “Ready for review” missing/duplicated | Single row, merged count **3** (= screening_complete 2 + review_pending 1) |
| Applications by role empty | Populated from current applications (Accounting 2, HR 2, Social Media Manager 2, …) |
| “Candidates” export unclear unit | Renamed **Candidate applications** (unit: application) |
| Raw delivery/provider errors in history export | Safe labels only: **WhatsApp conversation unavailable**, **WhatsApp conversation inactive**, **Email account needs reconnecting**, **Delivery failed** |

Raw diagnostics remain available only in restricted admin logs, not leadership exports.

---

## Live proof (`20260728T191018Z`)

| Assertion | Result |
|---|---|
| One “Ready for review” row with merged correct count | **PASS** (3) |
| No duplicate stage labels | **PASS** |
| Applications by role populated | **PASS** |
| Candidate applications label shown | **PASS** |
| Delivery history export only safe human issues | **PASS** |
| No raw technical/provider details | **PASS** |
| Counts/exports remain canonical | **PASS** |
| EN/AR + RTL | **PASS** |
| Health 200 | **PASS** |
| Rollback / restore | **PASS** |
| No unrelated mutations | **PASS** |

Evidence: `/opt/wathefni/production-evidence/reports-wave4-final-truth-export-cleanup/20260728T191018Z/live-proof.json`

---

## Rollback / restore

| Step | Result |
|---|---|
| Backend rollback (`reports_v1.py`, `reports_metrics.py`) | Health **200** |
| Dashboard rollback → previous asset | Health **200** |
| Backend restore | Health **200**; proof PASS |
| Dashboard restore | Health **200**; asset `dashboard-Bn-cWzgx.js` |

---

## Remaining limitations

- People count for candidate applications remains secondary metadata (not a separate column in this wave).
- Delivery-failure history is labeled as historical/admin; the channel column is simplified to WhatsApp/Email/Message for leadership readability.
- Role breakdown lists top roles (limit 50) with an “Unassigned role” bucket for applications without a mapped job.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Merged stage labels, no duplicates | **PASS** |
| Ready for review single merged count | **PASS** |
| Applications by role populated from canonical data | **PASS** |
| Candidate applications naming + application unit | **PASS** |
| Delivery history safe human labels only | **PASS** |
| No raw backend/provider/secret details in exports | **PASS** |
| Parity with canonical sources | **PASS** |
| EN/AR + RTL | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated mutations | **PASS** |

**Stop after Wave 4.**
