# HR Confirmation / File / Auth — physical canary matrix

**Stamp:** `20260810T183500Z`  
**Host:** prod API spine as Aziz (`96599338566`) · no iOS simulator/USB device on build host  
**Evidence:** this directory · `hr-cfa-out/` · `hr-cfa-out2/` · `seed-exercise.txt` · `pass2-exercise.txt` · `pass3-swap-docs.txt`  
**Frozen UX:** not reopened (defects reported only)

## Matrix

| Row | Verdict | Notes |
| --- | --- | --- |
| Attendance correction prepare→confirm | **PASS** | Seeded late exception on `WATHEFNI-9655237101`; SOD prepare→confirm `completed`; detail refresh OK; attendance restored after |
| Shift swap approve/reject confirm | **PASS** | Disposable `shift_swap_requests` reject; prepare→confirm `completed` → `rejected` (must not set `requested_by_phone` to acting HR — `self_swap_decision_forbidden`) |
| Onboarding Accept/Waive confirm | **PASS** | Waive passport on visual fixture; prepare→confirm `completed` |
| Document Mark reviewed confirm | **PASS** | Registry/`compliance_mark_reviewed` completed for `WATHEFNI-96550010001/work_permit` |
| HR Task Mark done confirm | **PASS** | `mobile_hr_task_resolve` → `done` (`3e293340-…`) |
| Onboarding file preview | **PASS** | Allowlisted `/dashboard/mobile/documents/files/786b0c82-…`; authenticated GET 200 |
| Document file preview/download | **PASS** | Allowlisted `/dashboard/mobile/documents/files/ddf26fa5-…` |
| Candidate CV open | **PASS** | Allowlisted preview path; authenticated GET 200 / 40044 bytes |
| Face ID enable/unlock + cancel→PIN | **BLOCKED** | No device on build host |
| auto-lock/background lock | **BLOCKED** | No device; static local-lock verify previously GREEN |
| Forgot PIN → operator email/password | **BLOCKED** | No device |
| safe-back + state refresh | **PARTIAL** | API refresh after attendance/swap/onboarding/task OK; UI safe-back needs device |
| EN/AR confirmation/auth/file states | **PARTIAL** | Static i18n present; physical locale toggle needs device |

## True release blockers

1. **Onboarding queue discoverability (FAIL)** — `mobile_onboarding_list` only scans the first ~90 `in_progress` rows. Fixture `WATHEFNI-9655237101` has `being_reviewed` but sits past that window, so the mobile queue returns **0** while detail/confirm works by key. HR cannot reach Accept/Waive from the queue for buried fixtures.
2. **Document Reviews queue empty (FAIL)** — `dashboard_compliance_payload` surfaces status `missing` (hist all-missing) even when `compliance_documents.status='needs_review'`. Mobile needs_review queue stays **0**; mark-reviewed mutation still works when targeted.

Neither is a frozen-UX reopen in this pass; both block honest physical “find → confirm” on device for those modules.

## Non-blockers

- Empty live queues before seeding = fixture scarcity, not product FAIL.
- Auth Face ID / auto-lock / Forgot PIN = **environment BLOCKED**, not product regression (known debt / prior freeze).
- Attendance list `in_exceptions=False` for seeded day after mutate did not block prepare→confirm.

## Hygiene follow-up

- Attendance verifier Wordmark check updated to cream `PageScreen + EditorialHeading` (Wordmark optional).

## Overall

**CONDITIONAL / API-spine PASS** for confirmation + authenticated files.  
**Not device-PASS.** Close physical Face ID/auto-lock/Forgot PIN + UI safe-back/EN·AR on owner device. Fix onboarding list pagination + compliance payload↔queue status alignment before calling Document/Onboarding queue flows release-ready.
