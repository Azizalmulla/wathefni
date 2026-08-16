# Wave C — entitlement blockers fix (local)

**Stamp:** `20260801T041426Z` (evidence) · matrix `20260801T041430Z`  
**Mode:** Local only (`wathefni_local_boundary`, `WATHEFNI_ENV=test`, `dry_run`). **No deploy. Wave D not started.**

**Evidence:** `ops/evidence/waveC-entitlement-blockers-fix-20260801T041426Z/`

---

## Verdict

| Suite | Result |
|---|---|
| Full Wave C entitlement / mutation matrix | **PASS 561 / 0 FAIL** |
| Former 15 FAIL gates (interviews tool + live tools + mobile assessments) | **PASS** |
| Unit / smoke / vitest regression pack | **PASS** |

---

## Root causes

1. **Live interview ActionSpecs gated on `pre_hiring`**  
   `schedule_interview`, `reschedule_interview`, `cancel_interview`, `send_interview_invite`, `get_interview_invite_status` used `module="pre_hiring"`. Because `pre_hiring` is not in `TOOLCALL_GATED_MODULES`, `_visible_tools` always offered them, and `_required_entitlements` reported `pre_hiring` instead of `interviews`.

2. **Assistant capability catalog fell back to `pre_hiring` when interviews OFF**  
   Live caps used `module="interviews" if interviews_on else "pre_hiring"`, so schedule/reschedule/cancel stayed offerable via always-on pre-hiring. `interviews_on` also OR’d `video_interviews`, conflating live vs async.

3. **Mobile always listed `assessments`**  
   `build_recruiting_workspace_capabilities` always included an `assessments` key (`enabled=False`). Boundary gates require the key to be **omitted** when the module is OFF. Live interview mobile features similarly tracked `pre_hiring` instead of `interviews`.

4. **Dashboard / workspace nav treated Interviews as pre-hiring**  
   `nav.interviews` used `moduleAnyOf: ['interviews', 'pre_hiring']` (TS + Python mirror) and `pageAvailableForSummary` allowed Interviews when only `pre_hiring` was on.

---

## Exact fixes

| Area | Change |
|---|---|
| `action_registry.py` | Live interview ActionSpecs → `module="interviews"` |
| `assistant_capability_catalog.py` | Live caps always `module="interviews"`; Teams/Meet use `live_interviews_on` |
| `operator_mobile.py` | Omit `assessments` when OFF; gate `interview_status` / `interview_notes` on `interviews` |
| `workspaceCapability.ts` + `workspace_capability.py` | Interviews nav → `interviews` \| `video_interviews` (not bare `pre_hiring`); composition excludes updated |
| `App.tsx` | `pageAvailableForSummary('interviews')` → interviews \| video_interviews |
| Smoke fixtures | HR1 / mobile authority mocks include `interviews` (+ `assessments` where needed) |

ON-module behavior, permissions, and tenant isolation paths are unchanged: when `interviews` / `assessments` are enabled, tools, nav, and mobile features still require the same permissions.

---

## Former 15 FAIL gates (requal)

| Gate | Before | After |
|---|---|---|
| `tool_schedule_interview_gated_by_interviews` | 8 FAIL | **8 PASS** |
| `assistant_live_tools_follow_interviews_module` | 4 FAIL | **8 PASS** (all tenants) |
| `mobile_omits_assessments_when_off` | 3 FAIL | **3 PASS** |

---

## Regression coverage added

**Backend / Assistant / API**
- `test_wave_c_entitlement_blockers.py` — ActionSpec modules, `_visible_tools` hide/show, execution fail-closed, mobile omit
- `test_assistant_capability_catalog.py` — live caps MODULE_OFF without interviews; AVAILABLE when ON
- `test_workspace_composition_matrix.py` — bare pre_hiring hides Interviews; assessments module gate
- `smoke-test-toolcall-orchestrator.py` — interviews module assertions + visibility/execution

**Desktop / mobile / EN+AR / direct URL**
- `workspaceCapability.test.ts` — Interviews not offered for bare pre_hiring; assessments direct-URL allowlist
- `App.test.tsx` — AR locale, mobile more-menu, `?page=interviews` remaps when interviews OFF; Assessments/Interviews labels absent EN+AR

Artifacts: `unit-tests/` under the evidence path.

---

## Matrix summary

```
{"suite": "waveC-local-mutation-requal-v1", "passed": 561, "failed": 0,
 "evidence": ".../waveC-local-mutation-requal-20260801T041430Z.json"}
```

Cleanup residue: **PASS** (log). No deploy. Wave D not started.
