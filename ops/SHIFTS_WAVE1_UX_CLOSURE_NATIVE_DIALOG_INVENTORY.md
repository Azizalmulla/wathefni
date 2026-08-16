# Browser-native dialog inventory — Shifts Wave 1 UX Closure

**Stamp context:** Shifts UX Closure (appended to Shifts Wave 1 freeze)  
**Payroll Wave 1:** frozen `20260804T080520Z` — **not modified** in this wave  
**Search scope:** `apps/wathefni-dashboard/src` (`window.prompt` / `window.confirm` / `window.alert` / bare `prompt|confirm|alert`)

## Summary

| Domain | Native sites found | Replaced this wave | Deferred |
|---|---:|---:|---:|
| Shifts | 2 | **2** | 0 |
| Attendance | 1 | **1** (low-risk) | 0 |
| Jobs (pre-hire) | 1 | **1** (low-risk) | 0 |
| Employees / Compliance docs | 6 | **4** (D3–D6 in Compliance Page Refinement Wave 1) | **2** (D1–D2 Employees-only) |
| Payroll | 0 | 0 | 0 (none present) |
| Leave / Onboarding | 0 | 0 | 0 |

---

## Replaced now

| # | Page / route | Action | File | Type | Mutation? | Risk | Replacement |
|---|---|---|---|---|---|---|---|
| 1 | Post-hire → Shifts → Schedule detail | Soft-cancel shift | `ShiftsWorkspace.tsx` `runCancel` | `prompt` (+ shared confirm) | Yes | Medium | `confirm.withReason` / `confirm` (record + impact + reason ≥3 when gate on) |
| 2 | Post-hire → Shifts → Requests → Reconciliation | Audited cancel | `ShiftsWorkspace.tsx` `resolveRecon` | `prompt` | Yes | Medium | `confirm.withReason` |
| 3 | Post-hire → Attendance → Import | Save column mapping name | `AttendanceImport.tsx` `saveMapping` | `prompt` | Yes (mapping metadata) | Low | `confirm.withReason` |
| 4 | Pre-hire → Jobs form sheet | Discard unsaved changes | `JobsForm.tsx` Cancel | `confirm` | No (nav guard) | Low | `confirm({…})` |
| 5 | Compliance / shared doc review | Reject document reason (D3) | `PostHire.tsx` `DocumentHrReviewButtons` | `prompt` → governed | Yes | Medium | `confirm.withReason` (min 3); Compliance Page Refinement Wave 1 `20260804T084521Z` |
| 6 | Compliance / shared doc review | Expiry + issue dates + correction reason (D4–D6) | `PostHire.tsx` `DocumentHrReviewButtons` | `prompt` → modal | Yes | Medium | Governed dates modal (inline validation, scroll lock, focus); same stamp |

---

## Deferred (exact inventory)

| # | Page / route | Action | File:loc | Type | Mutation? | Risk | Why deferred | Owning refinement |
|---|---|---|---|---|---|---|---|---|
| D1 | Employees → profile status | Pick designated approver number | `PostHire.tsx` ~1798 | `prompt` | Yes (`designated_approver_user_id`) | High | Needs people picker / structured select; dual-control UX | Employees Page / status dual-control amendment |
| D2 | Employees → activation handoff | Required handoff reason | `PostHire.tsx` ~1833 | `prompt` | Yes (`createEmployeeAppHandoff`) | Medium | Maps to `withReason` but sits in frozen Employees activation surface; avoid reopen | Employees activation UX amendment |

### Completed in Compliance Page Refinement Wave 1 (no longer deferred)

| # | Action | Status |
|---|---|---|
| D3 | Reject document reason | **Replaced** — `confirm.withReason` |
| D4 | Enter/correct expiry date | **Replaced** — governed dates modal |
| D5 | Enter/correct issue date | **Replaced** — same modal |
| D6 | Optional metadata correction reason | **Replaced** — optional field on same modal |

### Explicit non-items

- **Payroll / money-sensitive:** no browser-native dialogs found. Recorded for future controlled amendment only if any reappear. **Do not touch Payroll Wave 1 freeze.**
- **Leave / Onboarding:** already on shared confirm/`usePosthireAction` paths.
- **Irreversible hiring (hire/archive/role):** already on shared `ConfirmDialog` in recruiting surfaces (out of native-dialog set).

---

## Shared system used for replacements

- `ConfirmDialog` / `useConfirm` / `confirm.withReason` — `src/components/ConfirmDialog.tsx`
- App toast via `onNotice`
- Scroll lock + focus trap already in ConfirmDialog (`useBodyScrollLock`, `useOverlayFocus`)
- Optional `minReasonLength` added for audit-reason validation
