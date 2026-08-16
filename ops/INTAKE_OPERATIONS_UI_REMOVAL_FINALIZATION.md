# Intake Operations UI Removal — Finalization

**Date:** 2026-07-27 (UTC)  
**Stamp:** `20260727T153709Z`  
**Host:** `root@76.13.63.68`  
**Dashboard asset:** `dashboard-By4MxyA1.js`  
**Evidence:** `/opt/wathefni/var/evidence/intake-ops-ui-removal-20260727T153709Z/`  
**Scope:** Product UI only — no Candidates redesign, no color changes, no queue/worker/monitoring/backend processing changes

---

## Final PASS / FAIL

| Gate | Result |
|---|---|
| Intake Operations absent from sidebar for every role | **PASS** |
| Direct `?page=intake_operations` does not render the page | **PASS** (falls back to overview; page id removed) |
| Candidates has no Intake Operations banner/link | **PASS** |
| Frontend page component removed | **PASS** |
| Backend support APIs preserved | **PASS** (platform 200 / HR 403 unchanged) |
| CV queue / worker / concurrency unchanged | **PASS** |
| Postmark/journal monitoring still active | **PASS** |
| Health 200 | **PASS** |
| Rollback artifacts retained | **PASS** |
| No unwanted UI residue (`Intake Operations`, `intake_operations`, banner testid) | **PASS** (0 matches in shipped JS) |

**Verdict: PASS**

---

## Removed routes and components

| Removed | Path |
|---|---|
| Page component | `apps/wathefni-dashboard/src/components/candidates/IntakeOperationsPage.tsx` (**deleted**) |
| Nav item | `intake_operations` / “Intake Operations” from `navItems` in `App.tsx` |
| Page union member | `'intake_operations'` from `Page` type |
| Page labels/subtitles | Removed |
| Attention banner UI | `ProcessingAttentionBanner` removed from `CandidatesTable.tsx` and Candidates page |
| Frontend API helpers | `getIntakeOperations`, `getIntakeAttention` removed from `lib/api.ts` |
| Frontend types | `IntakeOperationsSummary`, `IntakeAttentionResponse` removed from `types.ts` |
| Attention fetch | Candidates loader no longer calls `/intake-operations/attention` |

**Preserved (unchanged):**

- Backend routes `GET /dashboard/prehire/intake-operations` and `/attention`
- Durable CV queue, workers, retries, leases
- `ops/inbound-ops-monitor.py` Postmark + journal delivery
- Canonical intake enqueue / attention math on the backend

---

## Navigation proof

Shipped JS: `/var/www/wathefni-dashboard/assets/dashboard-By4MxyA1.js`

| String | Matches in shipped JS |
|---|---|
| `Intake Operations` | **0** |
| `intake_operations` | **0** |
| `intake-operations-page` | **0** |
| `processing-attention-banner` | **0** |
| `Candidates` | present |

`?page=intake_operations` is not in `navItems`; initializer only accepts known nav ids (or `settings`), otherwise **overview**. No page body remains for Intake Operations.

Sidebar is driven solely by `navItems` → item removed for **all roles** (no platform-admin exception).

---

## Candidates proof

- No `ProcessingAttentionBanner`
- No `openPage('intake_operations')`
- No attention API poll on Candidates load
- General candidates with no job remain on Candidates only (unchanged list behavior)
- Legacy ImportReviewQueue banner remains only when unified Candidates is **off** (pre-unified import path) — not Intake Operations

---

## Backend / monitoring preservation proof

| Check | Result |
|---|---|
| Route definitions in `unified_candidates_routes.py` | Still present (`intake-operations`, `attention`) |
| Platform session → `/intake-operations` | **200** |
| Normal HR owner → `/intake-operations` | **403** `platform_support_only` |
| Attention endpoints | **200** for platform and HR (HR gets counts only; no UI consumer) |
| `wathefni-inbound-intake-worker.timer` | **active** |
| `wathefni-inbound-ops-monitor.timer` | **active** |
| `WATHEFNI_INTAKE_TENANT_CONCURRENCY` | **1** (unchanged) |
| Monitor delivery | journal written; Postmark configured (`skipped: unchanged` when alert set stable) |
| Audience | platform operations (not HR product UI) |

Evidence: `backend-api-still-available.json`, `backend-routes-still-present.txt`, `monitor-delivery-summary.json`, `concurrency.txt`.

---

## Production validation

| Step | Result |
|---|---|
| Health before | 200 / `status: ok` |
| Deploy release | `dashboard-intake-ops-removed-20260727T153709Z` → `/var/www/wathefni-dashboard` |
| Health after | 200 / `status: ok` |
| Grep residue | 0 for Intake Ops / banner identifiers |
| Local tests | `App.test.tsx` + `CandidatesTable.test.tsx` **14 passed** |

---

## Rollback

```bash
EVIDENCE=/opt/wathefni/var/evidence/intake-ops-ui-removal-20260727T153709Z
rm -rf /var/www/wathefni-dashboard
mkdir -p /var/www/wathefni-dashboard
rsync -a $EVIDENCE/dashboard-prev/ /var/www/wathefni-dashboard/
curl -fsS http://127.0.0.1:8010/health
```

Backend was not modified in this task; no orchestrator rollback required.

---

## Remaining notes

- Support/platform tooling should use monitoring (Postmark/journal) and backend APIs, not a dashboard page.
- Optional later cleanup: stop returning `link: "/intake-operations"` from the attention API (left unchanged per “backend APIs unchanged”).

---

## Stop

UI finalization complete. No Candidate profile work. No color changes. No queue/worker changes.
