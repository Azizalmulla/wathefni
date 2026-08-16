# WAVE1_PRODUCT_FULL_PASS

**Status:** ACCEPTED by owner 2026-08-11 — Wave 1 remains **FROZEN**  
**Evidence:** `ops/evidence/wave1-product-acceptance-20260811T192113Z` (preserve; do not delete)  
**Freeze:** `ops/WAVE1_PRODUCT_FREEZE.md`  
**Qualify:** `ops/qualify-wave1-product-acceptance-staging.sh`  
**Canary entitlement:** company-scoped **WATHEFNI** only — **do not broadly enable Wave 1 beyond WATHEFNI yet**

## Verdict

Wave 1 is frozen as the complete modular lifecycle:

**Requisition → Hire → Preboard → Onboard → Probation**

(with Jobs/approved-headcount gate, Offers bridge, 30/60/90, and Setup Console company policy ownership).

## Proven in this gate

1. **Product completeness** — HR Web + HR Mobile + Employee surfaces for Requisitions, Preboarding, Probation; Hire→Ready bridge; Onboarding auto-start path; Setup banners → Setup Console.
2. **Modularity matrix** — Requisitions+Hiring; Hiring+Offers without Preboarding; Preboarding without Recruiting; Preboarding+Onboarding; Probation without Onboarding; full suite. Disabled modules fail closed.
3. **Setup Console** — Wave 1 Hire→Ready policies (job gate, offer→preboard contract, probation policy/milestones, hire→onboarding auto-start) via `setup_console_wave1_policies` + `Wave1HireReadyPoliciesCard`.
4. **Canonical tasks** — `wave1_task_sync` emits `hr_tasks` for requisition approval / probation decision / preboard remind (same inbox SoT).
5. **Visual canary** — removable WATHEFNI seed (`ops-seed-wave1-visual-canary.py`) left populated for owner review.
6. **Regression** — lifecycle, requisitions (+surfaces), preboarding (+surfaces), hire-ready, probation (+surfaces), Phase A approvals + task/SLA, capability contracts, employment truth-sync units — all green.

## Visual canary (WATHEFNI) — keep until owner visual review

**Do not cleanup yet.** Keep fixtures available for owner inspection of Requisitions / Preboarding / Probation.

| Surface | Fixture |
|---|---|
| Requisition pending | `[Canary] Headcount Ops 096419` (`677eeae1-…`) |
| Requisition open | `[Canary] Open Eng 096419` (`e44cff0a-…`) |
| Preboarding | `WATHEFNI-VIS-096419` assignment `72c7e9a5-…` joining 2026-08-21 |
| Probation | `WATHEFNI-VIS-PRB-096419` case `45cf595e-…` |

**After owner visual review only:**  
`python3 ops-seed-wave1-visual-canary.py --cleanup` (staging orch, process-scoped flags).  
Preserve freeze docs + evidence. Do not broadly enable Wave 1 beyond WATHEFNI.

## Safe debt (documented — do not reopen Wave 1 for these now)

1. **Requisition N-step binding** — Wave 1 uses SoD single-step; platform `workflow_approvals` N-step exists but is not bound to requisitions yet.
2. **Live channel reminder fan-out** — Phase A SLA reminders remain `audit_only`; actionable state is canonical `hr_tasks`.
3. **Setup Wave1 card UI deploy** — API + card source proven; HR Web must ship/OTA the new Setup card for click-configure on staging/production canary.
4. **Broad production rollout** — remains beyond WATHEFNI canary until separate owner decision.

Wave 2 charter may schedule later platform polish for items 1–3; they are **not** Wave 1 reopen triggers.

## Genuine blockers

None for this stamp.
