# PRODUCTION_READINESS_R7_MOBILE_NATIVE_SAFETY_FULL_PASS

**Status:** QUALIFIED / frozen
**Stamp:** `PRODUCTION_READINESS_R7_MOBILE_NATIVE_SAFETY_FULL_PASS`
**Phase:** R7 — Mobile keyboard and native safety
**Date:** 2026-08-16
**Charter:** `ops/WATHEFNI_PRODUCTION_READINESS_CHARTER.md`
**Baseline:** `ops/PRODUCTION_READINESS_R1_AUDIT.md`
**Qualify:** `ops/qualify-production-readiness-r7-mobile-native-safety.sh`
**Freeze:** `ops/PRODUCTION_READINESS_R7_MOBILE_NATIVE_SAFETY_FREEZE_AMENDMENT.md`
**Evidence:** `ops/evidence/production-readiness-r7-mobile-native-safety-20260815T235419Z/`
**Prior freeze:** `PRODUCTION_READINESS_R6_SETUP_SELF_SERVICE_FULL_PASS` (R6 stays frozen; owner pause before R7 is lifted by this execution)

**Scope:** One shared keyboard-safe screen primitive across standalone HR Mobile and the Employee App / HR co-bundle, including Android; remove hardcoded offsets; then close P1-4…P1-9. Physical-device matrix (PH-5…PH-11) remains **RP**.

---

## 1. Result

| Gate | Result |
|---|---|
| HR Mobile vitest | **11 files, 45 passed, 0 failed** |
| Employee composition | **76 checks** |
| Employee capability foundation | **GREEN** |
| Push follow-through | **15 checks** |
| Employee a11y + i18n static scan | **21 checks** |
| R7 source contracts | **50 passed, 0 failed** (`R7_MOBILE_NATIVE_SAFETY_UNIT_PASS`) |
| Frozen unit regressions | R6 / R2 / R3 / R4 / R5A / R5C / Wave 4 — all unit PASS |
| Live staging health | **200** (`LIVE_HEALTH_OK`) |
| Open R7 blockers | **none** (physical proof remains RP) |

This stamp is **not** `PRODUCTION_READY` and authorises no broad rollout. R7 is frozen. R8 proceeds immediately per owner instruction.

---

## 2. R1 items closed in R7

| ID | Close |
|---|---|
| **PH-1** | Standalone HR Mobile `Screen` and employee HR `Screen` wrap `KeyboardAvoidingView` with `behavior="padding"` and `automaticallyAdjustKeyboardInsets`. Sign-in, leave rejection, and interview notes sit inside that primitive. |
| **PH-2** | Employee leave request opts into `keyboardInsets` on the inner scroller so Submit stays reachable. |
| **PH-3** | Shared `keyboardSafeBehavior()` is `'padding'` on every platform. Android is no longer `undefined`. |
| **PH-4** | PIN and HR Assistant no longer hardcode `keyboardVerticalOffset={0}`; they use `keyboardSafeOffset(insets.top)`. |
| **P1-4** | HR Mobile Leave queue is a capability-gated nav route (`/leave`) over existing `GET /dashboard/mobile/leave`. |
| **P1-5** | HR Mobile Tasks pass `allowed_actions` through as `actionsForItem` / `onAction` and POST `.../tasks/{id}/resolve`. |
| **P1-6** | `canOpen` hides Review chevrons on non-openable documents, today’s shift rows, and destination-less alerts. |
| **P1-7** | “Schedule interview” is honest: **View interviews** + note that scheduling is on HR Web. No invented mobile scheduler. |
| **P1-8** | Candidates list shows an advisory ranking note and a visible stage filter. Existing score sort is unchanged. |
| **P1-9** | Employee preboarding / probation are reachable from Home journey cards, Profile, and push (`FLOW_DEFAULT_PATHS`). They are **not** Home tiles and stay out of `MODULE_SURFACES`. |

Prefix destinations `/attendance/{id}` and `/documents/...` are admitted when the matching capability is granted.

---

## 3. What does not change

- Recruiting / Talent score authority stays advisory.
- Employee Home destination composition stays documents-only for the full suite.
- Physical Face ID, push delivery, and native RTL paint remain RP.
- R2–R6 and Wave 4 domain freezes stay frozen.

---

## 4. Qualification honesty

Source contracts prove keyboard wiring and product reachability. They do not claim a physical device was used. RP still owns PH-5…PH-11.
