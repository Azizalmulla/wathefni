# Hire → Ready Lifecycle Bridge (Wave 1)

**Status:** In qualification  
**Authority:** `wathefni-orchestrator/hire_ready_bridge.py`  
**Surfaces freeze (preboarding):** `ops/PREBOARDING_SURFACE_WAVE_FREEZE.md`

## What it does

Single orchestrator for optional integrations:

| Flow | Behavior |
|---|---|
| Offer accepted | Ensure `pending_start` + joining-date (canary writers) + optional Preboarding create |
| Manual future joiner | Preboarding without Recruiting (existing create path) |
| Joining-date change | Canonical `employees.start_date` + employment + preboard + onboarding planned_start |
| Preboarding ready → Hire | Convert assignment + advance **same** employment_id |
| Hire TX | Bridge before authority upsert; future dates stay `pending_start` |
| Onboarding auto-start | Company setting + `WATHEFNI_ONBOARDING_AUTO_START_WRITERS` (not global SEED) |
| Preboard ↔ Onboard dedupe | Overlap keys stamped / handoff |
| Cancel / no-show | Close provisional employment → hub `left` |

## Flags (process-scoped)

```text
WATHEFNI_HIRE_READY_WAVE1=on
WATHEFNI_HIRE_READY_COMPANIES=<company>

# Truth-sync writers — staging company canary ONLY after dry-run
WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS=on
WATHEFNI_EMPLOYMENT_TRUTH_SYNC_COMPANIES=<company>

# Onboarding auto-start writers
WATHEFNI_ONBOARDING_AUTO_START_WRITERS=on
# + company_settings.onboarding.auto_start_on_hire=true
# + company_modules.onboarding enabled
```

Empty truth-sync company allowlist ⇒ writers stay dark even if the global flag is on.

## pending_start invariants preserved

Never active before actual start · no payroll/attendance/leave/shifts eligibility · preboarding-only Employee App · excluded from active headcount · tenant/RBAC · same employment_id on convert · cancel closes cleanly.

## Qualify

```bash
ops/qualify-hire-ready-bridge-staging.sh
```

Smokes: `smoke-test-hire-ready-bridge.py` / `-db.py`
