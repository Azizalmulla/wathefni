# Production Readiness R5A — Capability Honesty Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FULL_PASS`
**Phase:** R5A — Wave 4/6 Capability Honesty Gate
**Date:** 2026-08-12
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md` (owner accepted; P0-1)
**Full pass:** `ops/PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r5a-capability-honesty-20260812T183621Z/`

This amends Wave 4/6 **customer-facing enablement UX only**. Domain authorities, tables, and internal env gates are unchanged.

---

## What freezes with R5A

These are now binding contracts. Changing any of them requires a written amendment, not a silent Setup default.

1. **`customer_enableable` is the only customer enablement truth.** It requires the HTTP adapter and the surfaces that module’s charter actually promises. A domain `FULL_PASS` stamp is not sufficient.
2. **Setup must not show an enable switch that produces nothing.** Unreleased capabilities are omitted from customer Setup. Card files may remain on disk for later unhide.
3. **Stored `enabled=true` is not usable.** Existing Wave 4 overlays and Wave 6 `*_company_settings` rows are preserved. Customer-facing Setup and runtime composition must not treat them as a live product.
4. **Env allowlists remain internal/runtime kill-switches.** They may open domain qualification. They must not make Setup claim the module is customer-usable.
5. **Catalog, Setup policy, and runtime must not contradict.** The nine unreleased keys stay out of `MODULE_CATALOG` until `customer_enableable`. Catalog SKUs (including Wave 5 `analytics`) stay enableable.
6. **Reserved future HTTP namespaces fail closed** (`404 capability_not_released`) until that module’s R5 surface slice replaces the stub. Stubs must not call domain libraries.
7. **Waves 1–3 Setup cards and Wave 5 Intelligence stay mounted.** R5A does not hide already-real modules.

## Wave 4 / Wave 6 product-acceptance UX amendment

Wave 4 C7 and Wave 6 C8 previously required Setup cards to be **wired** as the customer-facing policy owner. R5A amends that UX:

- Setup still **owns the policy store** (`setup_owns_wave4_policies` / `setup_owns_wave6_policies` remain true).
- Customer Setup **omits** the enable cards until `customer_enableable`.
- Internal qualification continues via env allowlists, domain `enable_company_*`, and Python `patch_wave4_module_policy` (not customer HTTP).

Domain math, modularity matrices, naming boundaries, and anti-duplication scans are not reopened.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. R4 (`PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`) remains frozen.
4. Waves 1–6 remain frozen as **domain authority**. Waves 4–6 remain not product-surface complete.
5. All Wave 4/6 runtime capability remains global-OFF and company-gated unless an internal allowlist is set.
6. `PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no rollout.
7. **R5B–R5J surface delivery does not start from this amendment.** Owner approval is required first.

## Deployment prerequisites

* Staging orchestrator must run `capability_readiness.py` + fail-closed HTTP registration + Setup PATCH refuse.
* HR Web Setup Console JS that omits the Wave 4/6 cards must ship with that backend so a customer never sees a dead enable switch.
* Do not remount `Wave4PerformanceTalentPoliciesCard` or Wave 6 policy cards without flipping `customer_enableable` for that capability.

## Owner review

R5A is complete and frozen. Stop.

Do not begin R5B automatically.
