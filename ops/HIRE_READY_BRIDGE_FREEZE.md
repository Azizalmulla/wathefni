# Hire → Ready Lifecycle Bridge — FREEZE

**Status:** FROZEN — `HIRE_READY_BRIDGE_FULL_PASS` accepted 2026-08-11  
**Evidence:** `ops/evidence/hire-ready-bridge-20260811T183406Z`  
**Contract doc:** `ops/HIRE_READY_BRIDGE.md`

## Frozen surface

| Artifact | Path |
|---|---|
| Authority | `wathefni-orchestrator/hire_ready_bridge.py` |
| Hire TX hook | `hire_operations.py` → `on_hire_employee_tx` |
| Offer accept hooks | `offer_service.py` → `on_offer_accepted` |
| Truth-sync canary | `employment_truth_sync.writers_enabled_for_company` |
| Convert/cancel/date fan-out | `preboarding_http.py` thin hooks |
| Smokes | `smoke-test-hire-ready-bridge.py` / `-db.py` |
| Qualify | `ops/qualify-hire-ready-bridge-staging.sh` |

## Freeze rules

1. Do **not** rewrite frozen Preboarding SM or surface contract via this bridge.
2. Hire must advance the **same** `pending_start` employment_id — never duplicate SoT.
3. Future joiners stay `pending_start` until actual start (never active early).
4. Truth-sync writers require **both** `WATHEFNI_EMPLOYMENT_TRUTH_SYNC_WRITERS=on` **and** a non-empty `WATHEFNI_EMPLOYMENT_TRUTH_SYNC_COMPANIES` allowlist — never systemd-global.
5. Onboarding auto-start requires company setting + `WATHEFNI_ONBOARDING_AUTO_START_WRITERS` — not global `WATHEFNI_ONBOARDING_SEED`.
6. Bridge remains dark by default: `WATHEFNI_HIRE_READY_WAVE1` + company allowlist.

Amendments require a dated note in this file + re-qualify.
