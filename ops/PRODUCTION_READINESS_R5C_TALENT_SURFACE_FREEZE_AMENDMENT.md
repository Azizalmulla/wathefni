# Production Readiness R5C — Talent Product Surface Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R5C_TALENT_SURFACE_FULL_PASS`
**Phase:** R5C — Talent Product Surface
**Date:** 2026-08-15
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R5C_TALENT_SURFACE_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r5c-talent-20260815T131524Z/`
**Amends:** R5A / R5B customer-facing Talent enablement only. Wave 4 domain authorities stay frozen.

This amends R5B for **Talent surfaces and Setup enablement**. Wave 6 remains under the R5A honesty gate. Performance enablement is unchanged.

---

## What freezes with R5C

These are now binding contracts. Changing any of them requires a written amendment.

1. **Talent is a product surface over C5–C6 only.** HTTP, HR Web, scoped Manager, and limited Employee App are adapters. No second profile / review / succession model. No frontend formula for a Talent score, HiPo, potential, or readiness.
2. **`customer_enableable("talent")` is true** because `http_ready + hr_web_ready + manager_surface_ready + employee_surface_ready` are all true. `mobile_ready` is false and **not required**. Setup remounts Talent policy enablement (`Wave4TalentPoliciesCard`, `scope="talent"`).
3. **Performance stays independently enableable.** `customer_enableable("performance")` remains true. Performance still strips Talent vocabulary. Talent works with Performance OFF. When Performance is ON, sealed outcomes may appear only as explicitly linked evidence. High performer ≠ high potential ≠ HiPo.
4. **No universal `talent_score`.** Potential, HiPo, readiness, skills, aspirations, mobility, and succession stay distinct dimensions. No hidden automatic promotion between them. No AI authority.
5. **Succession is target role → multiple successors.** Readiness is per target role. One employee may have different readiness for different roles. No universal readiness score.
6. **9-box is a derived presentation.** It uses configured axes, is not canonical Talent truth, does not overwrite potential or Performance, and disappears cleanly when inputs / config are unavailable.
7. **Talent HCM module ≠ recruiting `talent_pool`.** Namespaces, types, and UI language stay distinct. Talent works with Recruiting OFF. When Recruiting is ON, mobility may explicitly hand off. Interest ≠ application ≠ selection ≠ employment change. No silent candidate creation.
8. **Job Architecture stays unreleased.** Talent remains usable while JA is not customer-enableable. No duplicate Talent-specific job architecture.
9. **C3 development remains canonical.** Talent may reference development actions. It must not create a second development-plan authority. Learning stays optional / unreleased.
10. **Manager scope is fail-closed and server-enforced.** Empty `manager_scopes` is an empty list, not company-wide access. Manager scope alone does not imply `talent.sensitive`, `talent.review`, or `talent.succession`. No compensation. No unrestricted HiPo lists.
11. **Employee self-visibility is limited.** Career interests, aspirations, mobility preference, and allowed skills only. Potential, HiPo, succession slate, private readiness, 9-box, and confidential notes stay hidden by default.
12. **Disabled Talent** hides new surfaces, blocks new Talent work, preserves historical Talent state, and suppresses new Talent notifications via R4 (`flow=talent`).
13. **R5A honesty remains.** Domain `FULL_PASS` is still not customer enablement for any Wave 6 key. Only Performance (R5B) and Talent (R5C) have left the unreleased set.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3 (`PRODUCTION_READINESS_R3_DATA_SAFETY_FULL_PASS`) remains frozen.
3. R4 (`PRODUCTION_READINESS_R4_TRUTH_IN_UI_FULL_PASS`) remains frozen.
4. R5A (`PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FULL_PASS`) remains frozen, except the Talent enablement carve-out above.
5. R5B (`PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS`) remains frozen. Performance surfaces and Setup enablement are unaffected.
6. Wave 4 C5–C6 domain math, tables, and anti-duplication stay frozen.
7. Wave 6 domain authorities stay frozen and customer-unusable.
8. Env kill switches (`WATHEFNI_TALENT_KILL`, `WATHEFNI_TALENT_PROFILE_C5`, `WATHEFNI_TALENT_SUCCESSION_C6`) still win over Setup enablement.
9. `PRODUCTION_READINESS_R5C_TALENT_SURFACE_FULL_PASS` is **not** `PRODUCTION_READY` and authorises no broad rollout.

## Deployment prerequisites

* Staging / production orchestrator must ship `talent_http.py` + `talent_surfaces.py` registered **after** `employee_app_context` (not inside a swallowed early import).
* HR Web Talent workspace + Setup Talent card must ship with that backend.
* Employee App JS (OTA-eligible) must ship the limited Talent routes.
* Do not remount Wave 6 Setup cards without flipping that key's `customer_enableable`.
* Do not treat HR Mobile as a Talent enable gate.

## Owner review

R5C is complete and frozen. Stop.

Do not begin R5D Job Architecture automatically.
