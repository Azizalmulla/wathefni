# Wathefni Assistant — Grounded HR Operating Copilot

**Stamp:** `20260730T214056Z`  
**Verdict:** **PASS**  
**Environment:** Production (`root@76.13.63.68`)  
**Audit baseline:** `ops/evidence/assistant-page-ux-audit-20260731` (FAIL → addressed)  
**Product model:** Calm grounded HR operating copilot — capable across enabled modules, never ungrounded or uncontrolled

## Summary

Implemented the approved Assistant direction without a broad visual redesign. Preserved cream chat composition and `action_registry` mutation authority. Replaced WhatsApp chatbot framing with a dashboard HR copilot; wired per-turn capability catalog + `assistant_policy`; fixed dead chips / wording nav; added workflow preview/partial cards, real progress streaming + AbortController cancel, EN/AR RTL, overlay a11y, and React Profiler marks.

## Live proof

| Check | Result |
|---|---|
| Health | **PASS** `200` |
| Toolcall smoke | **PASS** |
| Capability unit tests | **PASS** |
| Live prover | **PASS** 31/31 |
| Dashboard AdminAI asset | `AdminAIPage-B7l25off.js` — RTL, Profiler, workflow, Stop |
| Live WATHEFNI offerable sample | assessments, calendar_events, candidate_workflow, candidates, google_meet, interviews_*, jobs, overview, ranking, reports |

Evidence: `live-proof.json`, `asset-markers.json`, `toolcall-smoke.txt`, `capability-tests.txt`.

## Exact files

### Backend
- `wathefni-orchestrator/assistant_capability_catalog.py` (**new**)
- `wathefni-orchestrator/assistant_policy.py`
- `wathefni-orchestrator/tool_call_orchestrator.py` (copilot prompt, policy, catalog, progress/cancel)
- `wathefni-orchestrator/action_registry.py` (restored + cancel/reschedule/reports + workflow cards/idempotency/partial)
- `wathefni-orchestrator/app.py` (artifacts, stream, workflow_card)
- `wathefni-orchestrator/test_assistant_capability_catalog.py`
- `wathefni-orchestrator/test_assistant_workflow_contract.py`
- `wathefni-orchestrator/smoke-test-toolcall-orchestrator.py`

### Dashboard
- `apps/wathefni-dashboard/src/pages/AdminAIPage.tsx`
- `apps/wathefni-dashboard/src/pages/AdminAIUxContract.test.tsx`
- `apps/wathefni-dashboard/src/App.tsx`
- `apps/wathefni-dashboard/src/lib/api.ts`
- `apps/wathefni-dashboard/src/types.ts`

### Ops
- `ops/deploy-assistant-copilot.sh`
- `ops/prove-assistant-copilot-live.py`

## Supported workflow matrix

| Capability | Tool / path | Confirm | Notes |
|---|---|---|---|
| Multi-step hiring workflow | `execute_candidate_workflow` | One preflight confirm | Steps + channels + people preview; partial ≠ full success; idempotency keys; retry prompt |
| Schedule interview + Meet + calendar | `schedule_interview` (also via workflow) | Yes + OCC | Google Meet when Google calendar configured |
| Reschedule / cancel interview | `reschedule_interview` / `cancel_interview` | Yes | `interview_service` authority; idempotent |
| Email / WhatsApp | `send_email` / `notify_candidate` / invite | Yes | Catalog marks not-configured when provider absent |
| Assessments | `send_assessment` | Yes | Module-gated |
| Candidate lifecycle | shortlist / hire / reject (+ batch/mixed) | Yes + OCC where required | Registry only |
| Jobs | list/search/create/pause/close/reopen | Mutations confirm | Inventory continuation → `assistant_prompt` (FE fixed) |
| Ranking | `rank_candidates` | Replay mode | Policy keeps module authority |
| Reports | `get_reports_metrics` | No (read) | `reports-contract-v2`; Overview ≠ Reports |
| Overview ops | `get_prehire_*` | No | Operational only |
| Post-hire | leave/attendance/shifts/onboarding/compliance/payroll/analytics | Per tool | Catalog + module + permission gated |

## Remaining capability gaps

1. **Teams Meet** — offered only when Microsoft calendar connection is `connected`; otherwise `enabled_but_not_configured` / not offerable. No parallel Teams creator inside chat.
2. **`schedule_interview` path** — still the registry Google Calendar (`gog`) executor on this train; cancel/reschedule use `interview_service`. Full prod-style schedule-via-`interview_service` unification is a follow-up, not required for this PASS.
3. **Email on tenants without provider** — correctly not offerable; Assistant must say setup is required.
4. **True token LLM streaming** — replaced fake drip with **real workflow progress phases** + single final reply delta; model tokens are not yet streamed mid-reasoning.
5. **Server-side cancel mid-tool** — AbortController stops client stream and signals `cancel_event` between tool loops; an in-flight atomic external API call may still finish.

## Tests

| Suite | Result |
|---|---|
| `test_assistant_capability_catalog.py` | PASS |
| Workflow preflight + partial (executor) | PASS |
| `smoke-test-toolcall-orchestrator.py` | PASS |
| `AdminAIUxContract.test.tsx` | PASS (5) |
| Production live prover | PASS 31/31 |

## Deployment / rollback

- **Deploy:** `ops/deploy-assistant-copilot.sh`
- **Backup:** `/opt/wathefni/backups/production-pre-assistant-copilot-20260730T214056Z`
- **Rollback:** `$BACKUP/ROLLBACK.sh`
- **Evidence:** `ops/evidence/assistant-copilot-20260730T214056Z/`

## PASS / FAIL

| Check | Result |
|---|---|
| Backend mutations via action_registry + confirmation/OCC | **PASS** |
| Capability catalog from modules/permissions/providers | **PASS** |
| assistant_policy on live turn (Reports vs Overview) | **PASS** |
| Grounded nav (no wording chips); assistant_prompt works | **PASS** |
| Workflow preview / partial / no false full success | **PASS** |
| Progress stream + AbortController cancel | **PASS** |
| Privacy: no raw cv_text in prompt | **PASS** |
| EN/AR RTL + overlay Escape/focus | **PASS** |
| React Profiler / interaction marks | **PASS** |
| Cream chat structure preserved (no broad redesign) | **PASS** |
| **Overall** | **PASS** |
