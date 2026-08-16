# Preboarding — Wave 1 Backend (authority)

**Status:** PREBOARDING_WAVE1_FULL_PASS (unit + staging DB) — **FROZEN**  
**Freeze:** `ops/PREBOARDING_WAVE1_BACKEND_FREEZE.md`  
**Evidence:** `ops/evidence/preboarding-wave1-20260811T180308Z`  

**Charter:** `ops/WATHEFNI_HCM_PHASE_A_WAVE1_BUILD_CHARTER.md` (W1.3)  
**Code:** `wathefni-orchestrator/preboarding.py`  
**SQL:** `wathefni-orchestrator/ops/sql/preboarding_wave1_v1.sql`  
**Smoke:** `wathefni-orchestrator/smoke-test-preboarding-wave1.py`  
**DB prove:** `wathefni-orchestrator/smoke-test-preboarding-wave1-db.py`  
**Qualify:** `ops/qualify-preboarding-wave1-staging.sh`

## Scope this slice

- `preboard_assignment` + `preboard_item` SM + Kuwait default template
- Readiness authority (derived `ready` / `blocked` — never cosmetic)
- Canonical `pending_start` attach + joining_date write
- Tasks/SLA via Phase A spine (`preboard_item`, `preboard_readiness`)
- Audit events, manager scope, tenant isolation, module-off
- OPTIONAL helpers: offer auto-create + onboarding handoff (gated; offer path not globally wired)
- **No** Preboarding UI (HR Web / Mobile / Employee App)

## Rollout flag (fail closed)

1. `WATHEFNI_PREBOARDING=on`
2. `WATHEFNI_PREBOARDING_COMPANIES=<CSV>` (empty = nobody)
3. `preboarding_settings.enabled=true` **or** `company_modules.preboarding.enabled=true`

## State machines

```
assignment: not_started → in_progress → ready | blocked → converted | cancelled
item:       pending → in_progress → done | waived | blocked
```

## Critical invariants

- `pending_start` remains non-active (no ESS/pay/time/leave/shifts eligibility from Preboarding)
- No duplicate employee/employment on convert
- Works without Recruiting
- Offers auto-create only when OPTIONAL contract active
- Onboarding handoff dedupes overlapping item keys (no duplicate Civil ID tasks)
- `ready` derived from required items/gates only
- cancel / no_show / withdrawn close cleanly with audit

## Rollback

1. `WATHEFNI_PREBOARDING=off`
2. Remove company from allowlist
3. `UPDATE preboarding_settings SET enabled=false …`
4. Retain tables; do not DROP
5. Close open provisional employments via lifecycle/cancel paths as needed

## Out of scope

- Polished HR Web / HR Mobile / Employee App surfaces
- Global offer-accept wiring in production systemd
- Truth-sync writers
