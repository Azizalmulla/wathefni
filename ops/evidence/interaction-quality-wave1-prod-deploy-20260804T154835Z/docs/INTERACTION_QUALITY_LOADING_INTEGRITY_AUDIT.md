# Wathefni Interaction Quality & Loading Integrity Audit

**Stamp:** `20260804T154835Z`  
**Evidence:** `ops/evidence/interaction-quality-wave1-prod-deploy-20260804T154835Z/`  
**Live:** `dashboard-fA_AOGGG.js` · `PostHire-BkppdKlQ.js` · `button-6OiZkJ3m.js` · `InterviewsPage-DNde7GfB.js`  
**Backup / rollback:** `/opt/wathefni/backups/production-pre-interaction-quality-wave1-20260804T154835Z/`  
**Smoke:** `INTERACTION_QUALITY_WAVE1_SMOKE_OK` (+ Settings + Activity rechecks green)  
**Scope:** Pre-hiring + post-hiring dashboard UI interactions  
**Not in scope:** Final palette pass · backend authority · frozen contract redesign · high-risk payroll/hiring/destructive workflows  
**Shifts:** Findings remain open for owner review — current freeze is **not** final design approval

---

## Verdict

| Gate | Result |
|---|---|
| Audit ledger | **GO** |
| Shared + low-risk local fixes | **GO** (deployed) |
| High-risk payroll / hiring / destructive | **NO-GO** (not started) |
| Shifts design closure | **OPEN** (owner review) |
| Final palette | **NO-GO** (not started) |

---

## Interaction standard (target)

- Local pending on the affected control/row/modal/section  
- Keep existing data visible while refreshing  
- Disable repeat submit while pending  
- Keep modals open until confirmed success (when async `run` is used)  
- Update only affected data where possible  
- Preserve scroll, filters, expanded rows, focus  
- Clear success / failure / cancel feedback  
- Stable skeletons only for genuine initial load  
- No layout shift while controls are pending  

---

## Findings ledger

| ID | Route / surface | Interaction | Sev | Root cause | Local/Shared | Recommended fix | Must wait? | Wave 1 |
|---|---|---|---|---|---|---|---|---|
| IQ-01 | All `useConfirm()` flows | Confirm → mutate gap | P0 | Dialog settles before mutation | Shared | Optional `run` keeps dialog open | No (chrome) | **Shipped** (opt-in API) |
| IQ-02 | Leave | Approve/decline drawer | P0 | `useEffect([data])` cleared selection | Local | Rematch by `leave_id` | No | **Shipped** |
| IQ-03 | Shell / pre-hire | Global busy banner | P0 | Always “Refreshing hiring data…” | Shared | Prefer action notice / Working… | No | **Shipped** |
| IQ-04 | Interviews | Blank list / drawer slam | P0 | No `keepPreviousData`; clear selection mid-fetch | Shared + local | keepPrevious + sticky snapshot | No | **Shipped** |
| IQ-05 | Assessments send rows | Confirm then all rows freeze | P0 | Global busy + no per-row pending | Shared + local | Per-row pending chrome | Cancel/resend **wait** | Residual |
| IQ-06 | `useModuleData` lists | Search/range wipe | P1 | `setData(null)` on loader change | Shared | Soft-keep | Soft-keep yes | **Shipped** |
| IQ-07 | Activity | Filter spinner wipe | P1 | Full loading replaces list | Local | Soft refreshing | No | **Shipped** |
| IQ-08 | Ranking | Job switch stale cards | P1 | Prior ranking kept under new title | Local + App | Clear before load | No | **Shipped** |
| IQ-09 | Interview action modal | Backdrop during submit | P1 | Ungated `onClose` | Local | Gate by `submitting` | No | **Shipped** |
| IQ-10 | Add-to-job dialog | Backdrop mid-submit | P1 | Ungated `onClose` | Local | Gate by `busy` | No | **Shipped** |
| IQ-11 | Shared `Button` | Pending resize | P1 | No pending slot | Shared | `pending` + aria-busy | No | **Shipped** |
| IQ-12 | Shifts | Filters / drawer / confirm | P1 | Undebounced filters, strip jump, incomplete confirm | Local | Debounce + sticky + confirm path | **Yes — Shifts owner** | Residual / open |
| IQ-13 | Settings role/deactivate | Confirm → mutate | P2 | Same as IQ-01 | Shared | Opt into `run` later | Authority **wait** | Residual |
| IQ-14 | Compliance / docs modals | Close timing | P1/P2 | Varies | Local | Keep open until success | Destructive **wait** | Residual |
| IQ-15 | Payroll surfaces | Pending chrome | P2 | Inconsistent spinners | Local | Pending UI only | Money/export **wait** | Residual |
| IQ-16 | Hire / reject / offers / job close / intake / calendar cancel | Lifecycle | P0–P1 | Pending gaps | Mixed | Pending chrome only | **Yes — owning modules** | Residual |

---

## Implemented in Wave 1

1. `Button` `pending` prop  
2. `ConfirmDialog` optional async `run` + `data-interaction-confirm`  
3. Shell busy notice honesty (`data-interaction-shell-busy`)  
4. Interviews `keepPreviousData` + sticky selection snapshot  
5. Activity soft refresh (`data-activity-refreshing`)  
6. Leave selection rematch  
7. `useModuleData` / Leave soft-keep (no wipe on param change)  
8. InterviewActionDialog + AddToJobDialog backdrop guards  
9. Ranking clear on job switch  

---

## Residual ledger (still open)

| Item | Owner / next step |
|---|---|
| Wire high-value confirms through `confirm({ run })` (Settings role, Leave approve, etc.) without changing authority | Module owners — opt-in only |
| Assessments per-row pending + send/cancel policy | Assessments module |
| Hire / reject / offer / job publish-close pending chrome | Hiring module |
| Shifts filter debounce, sticky drawer, `needs_confirmation` completion | **Shifts owner review (open)** |
| Payroll / statutory / payslip pending polish | Payroll — money authority wait |
| Document “Correct dates” modal: close only after success | Compliance / Employees docs |
| `usePosthireAction` global busy + hold through reload | Shared post-hire follow-on |
| Leave `run()` fire-and-forget → return Promise / pending key before confirm | Leave |
| Attendance Ops deep-link re-scroll on soft reload | Attendance |
| Overview work-queue Mine↔Company false empty | Overview |
| Reports export per-card pending; Candidates save-view pending | Reports / Candidates |
| Intake/import: narrow invalidate vs `refreshEverything` | Candidates intake (authority wait for archive semantics) |
| Suspense / profile fallback polish | App shell |
| Split App global `busy` into per-action registry | Shared follow-on (higher risk than this wave) |
| Final palette pass | Explicitly not started |

Audit sources: [post-hire audit](51caf086-c792-499f-9836-85b6252a94ad), [pre-hire audit](0d7f51a6-df11-4fa6-ba53-b0f7918527a5). Wave 1 already shipped against their shared P0s; no further deploy from these completions.

---

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-interaction-quality-wave1-20260804T154835Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-interaction-quality-wave1-20260804T154835Z
```
