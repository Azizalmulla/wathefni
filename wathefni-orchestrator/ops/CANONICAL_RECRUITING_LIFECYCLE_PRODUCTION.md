# Canonical Recruiting Lifecycle — Production Enablement Record

**Date:** 2026-07-15  
**Result:** ENABLED and verified. Stopped after production verification.

## Pre-enable confirmations

| Item | Confirmation |
|---|---|
| Leave `request_leave` 403 | Unaffected — lifecycle commits touch no leave/posthire files and no `request_leave` symbols |
| Artifact / commit | `1369e96` (deploy migrate env fix) on top of lifecycle `fa9e94d`…`cd4f606`; tip after smoke fix `f902667` |
| Pre-deploy backup | `/opt/wathefni/backups/predeploy-20260715T180333Z` (+ daily `20260715T180329Z`) |
| Behavioral switch | Only `WATHEFNI_CANONICAL_LIFECYCLE` |
| Rollback | Verified: unset drop-in → service flag cleared → `canonical_lifecycle_enabled()=False` → health 200; then re-enabled |
| Bulk status rewrite | None — legacy statuses still present in production distribution |

## Production hashes

| File | sha256 |
|---|---|
| `app.py` | `8b627da4c212bb7cd71995f1a38ab5aaac8d46ccdceb8b600f33cbdc77668715` |
| `recruiting_lifecycle.py` | `19874f370235450196baf2d80bf070395b5830cc6ab9cc26047e575039ce0a4a` |
| `action_registry.py` | `c4e6f6e4244333e26d98f0ba152103e3261c9cbc84752a3f02da641b19d37d76` |
| `tool_call_orchestrator.py` | `aa2f4d260141b07656308abb4f8a3bb0c556a1c192e100e1e64f48adc0f14375` |
| `operator_mobile_data.py` | `0aa84f3794d05d9d741475b9a381d83a9fcdc42f69b645555491653aca6aef0e` |
| Deploy artifact (staging-green) | `1acc6a33f5cfbdba758fd241cc86f0c11b10f36b051ebe1b0f76c53a51ad78f5` |

## Migration

`ensure_schema(force=True)` with production runtime binding → `prod schema ok`  
Tables/indexes present: `application_lifecycle_events`, `conversation_application_bindings`, `hr_tasks_ready_for_review_open_uq`

## Flag

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/canonical-lifecycle.conf`  
`Environment=WATHEFNI_CANONICAL_LIFECYCLE=true`  
Service active, health 200

## Production-safe smoke

`smoke-test-canonical-lifecycle-prod.py` → **21 passed, 0 failed**

Covered: legacy read mapping, existing candidate readability, ambiguous WhatsApp reject, conversation-bound `app_key`, valid shortlist, stale reject, hire blocked from `ready_for_review`, ready-task once, tenant isolation, no interviews/employees/outbound/decision audits left, synthetic cleanup.

## Side-effect proof

No candidate messages, decisions, interviews, or employee records created by the smoke (before/after counters + cleanup checks).
