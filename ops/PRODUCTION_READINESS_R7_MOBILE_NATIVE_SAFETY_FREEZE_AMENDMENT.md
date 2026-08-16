# Production Readiness R7 — Mobile Keyboard and Native Safety Freeze Amendment

**Stamp:** `PRODUCTION_READINESS_R7_MOBILE_NATIVE_SAFETY_FULL_PASS`
**Phase:** R7 — Mobile keyboard and native safety
**Date:** 2026-08-16
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Full pass:** `ops/PRODUCTION_READINESS_R7_MOBILE_NATIVE_SAFETY_FULL_PASS.md`
**Evidence:** `ops/evidence/production-readiness-r7-mobile-native-safety-20260815T235419Z/`
**Amends:** R1 PH-1…PH-4 and P1-4…P1-9. R6 remains frozen. Physical PH-5…PH-11 remain RP.

---

## What freezes with R7

These are now binding contracts. Changing any of them requires a written amendment.

1. **One shared keyboard-safe contract** lives in `keyboardSafe.ts` on both mobile apps: `behavior` is always `'padding'`. Android is never left without avoidance.
2. **HR `Screen` primitives** (standalone and employee HR co-bundle) wrap content in that contract and enable `automaticallyAdjustKeyboardInsets`.
3. **Employee `PageScrollView` keyboard insets** apply on every platform when a form opts in. Default remains off so ordinary pages do not grow a phantom cream inset.
4. **Hardcoded `keyboardVerticalOffset={0}` is banned** on PIN and HR Assistant. Offset is `keyboardSafeOffset(topInset)` (iOS inset, Android 0).
5. **HR Mobile Leave** is a first-class capability-gated queue (`leave_approvals` → `/leave`) over the existing backend leave list/detail/decision. Home priorities are no longer the only entry.
6. **HR Mobile Tasks** must pass backend `allowed_actions` through as real actions. Resolve uses `POST /dashboard/mobile/tasks/{task_id}/resolve` with `{ status, expected_status }`. Preview fixtures may remain read-only.
7. **Dead Review chevrons are forbidden.** `ActionableCard` / `OperationalListView` attach `onPress` only when `canOpen` says the row has a real destination.
8. **Interview scheduling is not invented on mobile.** The affordance may open the interview list and must say scheduling is on HR Web.
9. **Candidate ranking is advisory.** The list may show the existing score sort and a stage filter. It must not invent a new Talent score.
10. **Employee preboarding / probation** are journeys, not Home tiles. Reachable from Home journey cards, Profile, and push defaults. `MODULE_SURFACES` and `homeDestinations` stay unchanged.
11. **Physical-device proof remains RP.** R7 source contracts do not substitute for Face ID, push delivery, or native RTL paint.
12. **R7 does not reopen** Wave 4 C1–C6, PT1–PT7, or R2–R6 except a genuine correctness/security blocker.

## What does not change

1. R2 (`PRODUCTION_READINESS_R2_SECURITY_FULL_PASS`) remains frozen.
2. R3–R6 remain frozen.
3. Recruiting / Talent / Performance domain authorities remain frozen.
4. `PRODUCTION_READINESS_R7_MOBILE_NATIVE_SAFETY_FULL_PASS` is **not** `PRODUCTION_READY`.

## Owner review

R7 is complete and frozen. R8 proceeds immediately per owner instruction. Stop for owner review after R8. Do not begin R9 automatically.
