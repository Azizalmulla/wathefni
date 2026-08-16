# HR mobile — Confirmation / File / Auth qualification matrix

Stamp: `20260810T181353Z`  
Mode: **audit only — no redesign**  
Trigger: Employee Profile freeze complete (`20260810T180148Z`); canary Next = this matrix

## Verdict: **CONDITIONAL — static contracts mostly green; physical canary still required**

This is **not** another module cream wave. It is the cross-cutting pre-release matrix: decision confirmation, authenticated file open, and HR local-lock/auth overlays.

Employee Profile remains **PASS / FROZEN** (OTA `66eab204-…`). Do not reopen Profile / E360.

---

## Bucket 1 — Confirmation UX

| Surface | Pattern | Static | Physical |
| --- | --- | --- | --- |
| Leave | ConfirmationSheet + route SOD | **PASS** (frozen cream) | **PASS** stamped |
| Candidate | ConfirmationSheet + route SOD | **PASS** (frozen cream) | **PASS** stamped |
| Attendance | `useServerConfirmation` + sheet | Sheet wired | **Pending** canary prepare→confirm |
| Shift swap | `useServerConfirmation` + sheet | Sheet wired | **Pending** approve/reject |
| Onboarding | `useServerConfirmation` + sheet | Sheet wired; demo Alert blocks | **Pending** Accept/Waive |
| Documents | Client ConfirmationSheet + `expected_status` (not `useServerConfirmation`) | Sheet + stale field present | **Pending** Mark reviewed |
| Tasks | Client ConfirmationSheet + `expected_status` | Sheet wired | **Pending** Mark done |
| Settings sign-out | Confirm dialog (non-sheet) | Settings verify GREEN | Soft reconfirm |

Shared chrome: `src/hr/components/primitives.tsx` · `src/hr/api/useServerConfirmation.ts`

**Honesty note:** Documents/Tasks use client confirm + `expected_status` rather than shared `useServerConfirmation` — intentional existing pattern; do not unify in this matrix without an owner wave.

---

## Bucket 2 — Authenticated file open

| Check | Result |
| --- | --- |
| Path allowlist | `openAuthenticatedFile` requires `/dashboard/mobile/*` only |
| Onboarding preview | Caller present; demo Alert when demo |
| Documents preview/download | Caller present; demo Alert when demo |
| Candidate CV | Caller in `app/hr/candidates/[appKey].tsx` (frozen detail) |
| Physical open-on-device | **Pending** (iOS Files / Quick Look) |

---

## Bucket 3 — Auth / local lock

| Check | Result |
| --- | --- |
| `verify-hr-local-lock-parity` | **GREEN** |
| `verify-hr-settings-operator-device` | **GREEN** |
| Physical Face ID / auto-lock / Forgot PIN recovery | **Pending** (debt: `ops/HR_MOBILE_LOCAL_LOCK_CONTRACT_DEBT.md`) |
| Phase 6 screen-lock | Out of scope |

---

## Static gate anomalies (not matrix blockers)

| Gate | Issue |
| --- | --- |
| `verify-hr-attendance-exceptions.py` | **FAIL** `Wordmark + EditorialHeading` on queue — script expects Wordmark; cream queue may have dropped it. Fix verify or restore Wordmark in a tiny attendance hygiene pass — **not** part of Profile / this matrix redesign |

Other module verifies (shifts/onboarding/documents/tasks/settings/local-lock): **GREEN** at stamp time.

---

## Freeze after this matrix?

**No single freeze** for “confirmation/file/auth” as a product surface. When physical canary is green:

1. Stamp PASS row on canary log for this matrix.
2. Keep module freezes as-is.
3. Close local-lock debt item “Physical Face ID QA on HR”.

**Out of scope:** Profile redesign, E360, module cream remakes, Phase 6, inventing unified SOD for Documents/Tasks.

Evidence: this folder (`static-scan.txt`, verify-*.txt).
