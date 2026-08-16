# Post-hire mutation integrity audit

**Stamp:** `20260804T062017Z`  
**Evidence:** `ops/evidence/posthire-mutation-integrity-20260804T062017Z/`  
**Gate:** mutation integrity fix only — **not** a Needs Attention UX freeze iteration  
**Hold:** no further Needs Attention page refinement until owner confirms workflows

## Root cause

Production runs `WATHEFNI_ASSISTANT_MUTATIONS=0` (Platform Assistant Wave 1). The kill lived in shared `_execute_tool`, which `/dashboard/posthire/action` also uses with `channel=web_dashboard`.

Ordinary Onboarding / Leave / Attendance / Shifts buttons were denied with:

> Mutations are disabled for this assistant session…

UI `canMutate` only checked module permissions + `hr_mutate_enabled`, so buttons stayed clickable.

## Forensic (owner clicks ~2026-08-04 05:56 UTC)

| Tool | Count | Outcome | Data changed? |
|---|---|---|---|
| `reschedule_onboarding` | 2 | `assistant.mutation_blocked` + `action_results` failed | **No** |
| `cancel_onboarding` | 3 | same | **No** |
| `onboarding_mark_item` | 1 | same | **No** |
| `onboarding_audit_events` in window | 0 | — | **No** |

**No production onboarding records were mutated by those clicks.**

## Fix

1. `_execute_tool`: skip assistant mutation kill when `channel=web_dashboard` or `metadata.dashboard`
2. `run_dashboard_registry_action`: explicit `mutations_disabled` → dashboard-safe error (never success)
3. Client `usePosthireAction`: Promise `run`, confirm dismiss toast, `options.confirm` for Onboarding Cancel/Reschedule/Mark/Remind, Reschedule closes only on success

Assistant / WhatsApp mutations remain killed while `WATHEFNI_ASSISTANT_MUTATIONS=0`.

## Scope after fix

| Surface | Assistant kill applies? |
|---|---|
| Platform Assistant / WhatsApp mutations | **Yes (intended)** |
| Dashboard `/posthire/action` sensitive tools | **No** (normal entitlements) |
| Add employee / Org / Settings REST | Never did |

## Tests

- `wathefni-orchestrator/smoke-test-posthire-mutation-integrity.py`
- `apps/wathefni-dashboard/src/posthire/PosthireMutationIntegrityContract.test.ts`

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-posthire-mutation-integrity-20260804T062017Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-posthire-mutation-integrity-20260804T062017Z
```
