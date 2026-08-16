# Probation Wave 1 — Backend Authority

**Status:** In qualification  
**Authority:** `wathefni-orchestrator/probation.py`  
**SQL:** `wathefni-orchestrator/ops/sql/probation_wave1_v1.sql`

## Scope (backend only — no surfaces)

| Entity | State machine |
|---|---|
| `probation_case` | `scheduled → active → under_review → confirmed \| extended \| failed` (+ `cancelled`) |
| `probation_milestone` | `pending → completed \| skipped \| overdue` |

Default Kuwait template: **30 / 60 / 90** day milestones.

## Flags

```text
WATHEFNI_PROBATION=on
∧ company in WATHEFNI_PROBATION_COMPANIES
∧ probation_settings.enabled OR company_modules.probation
```

Dark by default. No systemd-global enable. No Probation UI in this wave.

## Optional integrations

- `probation.auto_plan_on_hire` — soft hook from Hire→Ready bridge when employment activates
- `probation.sync_from_offer` — truth-sync canary (separate writers flag)
- `probation.start_mode=onboarding_complete` — defers auto-plan

## Qualify

```bash
ops/qualify-probation-wave1-staging.sh
```
