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
| Employees / Compliance docs | 6 | 0 | **6** |
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

---

## Deferred (exact inventory)

| # | Page / route | Action | File:loc | Type | Mutation? | Risk | Why deferred | Owning refinement |
|---|---|---|---|---|---|---|---|---|
| D1 | Employees → profile status | Pick designated approver number | `PostHire.tsx` ~1798 | `prompt` | Yes (`designated_approver_user_id`) | High | Needs people picker / structured select; dual-control UX | Employees Page / status dual-control amendment |
| D2 | Employees → activation handoff | Required handoff reason | `PostHire.tsx` ~1833 | `prompt` | Yes (`createEmployeeAppHandoff`) | Medium | Maps to `withReason` but sits in frozen Employees activation surface; avoid reopen | Employees activation UX amendment |
| D3 | Employees / Compliance docs | Reject document reason | `PostHire.tsx` `DocumentHrReviewButtons` ~2546 | `prompt` | Yes | Medium | Shared component; pair with Approve already on `useConfirm` | Document review UX amendment |
| D4 | Employees / Compliance docs | Enter/correct expiry date | `PostHire.tsx` ~2564 | `prompt` | Yes | Medium | Date form modal (not reason dialog) | Document review UX amendment |
| D5 | Employees / Compliance docs | Enter/correct issue date | `PostHire.tsx` ~2565 | `prompt` | Yes | Medium | Same as D4 | Document review UX amendment |
| D6 | Employees / Compliance docs | Optional metadata correction reason | `PostHire.tsx` ~2566 | `prompt` | Yes | Low–Med | Bundle with D3–D5 form modal | Document review UX amendment |

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
