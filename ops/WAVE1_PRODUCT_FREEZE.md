# Wave 1 Product — FREEZE

**Status:** FROZEN — `WAVE1_PRODUCT_FULL_PASS` **accepted by owner 2026-08-11**  
**Pass doc:** `ops/WAVE1_PRODUCT_FULL_PASS.md`  
**Evidence:** `ops/evidence/wave1-product-acceptance-20260811T192113Z` (preserve)  
**Qualify:** `ops/qualify-wave1-product-acceptance-staging.sh`

## Frozen modular lifecycle

`Requisition → Job gate → (Offers) → Preboard → Hire → Onboard → 30/60/90 → Probation`

## Frozen artifacts (additive product layer)

| Artifact | Path |
|---|---|
| Setup Wave 1 policies | `wathefni-orchestrator/setup_console_wave1_policies.py` |
| Canonical task sync | `wathefni-orchestrator/wave1_task_sync.py` |
| Setup UI card | `apps/wathefni-dashboard/src/setup-console/Wave1HireReadyPoliciesCard.tsx` |
| Visual canary seed | `wathefni-orchestrator/ops-seed-wave1-visual-canary.py` |
| Product smokes | `smoke-test-wave1-product-acceptance.py` / `-db.py` |

Prior freezes remain authoritative for domain SMs:

- `ops/REQUISITIONS_SURFACE_WAVE_FREEZE.md`
- `ops/PREBOARDING_SURFACE_WAVE_FREEZE.md`
- `ops/HIRE_READY_BRIDGE_FREEZE.md`
- `ops/PROBATION_WAVE1_BACKEND_FREEZE.md` / `ops/PROBATION_SURFACE_WAVE_FREEZE.md`
- `ops/WAVE1_LIFECYCLE_FULL_PASS.md` (authority chain)

## Freeze rules

1. Wave 1 stays frozen. Do **not** reopen for documented safe debt.
2. Keep company-scoped canaries only — never systemd-global enable for Wave 1 Hire→Ready flags. **Do not broadly enable beyond WATHEFNI** without a separate owner decision.
3. Do not invent a second inbox; Wave 1 events continue through `hr_tasks` + domain events.
4. Disabled modules must fail closed (nav + API); do not leave dead CTAs.
5. Setup Console owns Wave 1 company policy; do not regress to env-only customer configuration for gate/auto-start/probation/preboard contracts.
6. Visual canary fixtures stay until owner visual review completes; then cleanup only the synthetic fixtures — preserve freeze/evidence.

## Documented safe debt (carry forward — not Wave 1 reopen)

See `ops/WAVE1_PRODUCT_FULL_PASS.md` § Safe debt. Next work is **Wave 2 charter review** (`ops/WATHEFNI_HCM_WAVE2_WORKFORCE_TRUTH_BUILD_CHARTER.md`) — implementation only after that charter is reviewed.

Amendments to frozen Wave 1 SMs require a dated note here + re-qualify.
