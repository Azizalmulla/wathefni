# Kuwait Pilot Document Journey — Dashboard Reconciliation Staging Green

**Status:** staging-green (reconciled dashboard)  
**Production:** **untouched** — still foundation freeze `73cccafd…`; journey module **absent** on prod; `/var/www` still `dashboard-CfaEseRj.js`  
**Date:** 2026-07-25 (Kuwait)  
**Superseded artifact (do not re-promote):** `4be5298e769576cb691b750ec9513c190d32adb13e9bddf2ebb004f694ab85d7`  
**New staging-green artifact:** `6018796d265c1a8d77e3bd880849b8e65f627003dc20ca544403db426d2097e1`  
**Freeze:** `ops/KUWAIT_PILOT_DOCUMENT_JOURNEY_DASHBOARD_RECONCILIATION_FREEZE.txt`  
**Stop:** do **not** deploy to production until explicit owner approval of **exactly** this new SHA.

---

## Verdict

One contained dashboard reconciliation restored the frozen Interviews EN/AR accessibility copy from the current production-green dashboard into a build that still carries the approved Kuwait document-journey PostHire UX. Staging qualification is green: Interviews **45/45**, document journey **68/68**, dashboard tests **49/49**, typecheck/build green, full frozen regressions green. **Production untouched. Stop.**

---

## Root cause

The prior staging-green dashboard dist (`dashboard-CdJ5YPdj.js`) included document-journey PostHire/api changes but was built from a `recruitingLifecycle.ts` that had dropped the Interviews queue/agenda/a11y copy keys present in production-green `dashboard-CfaEseRj.js`. Promoting that dist to `/var/www` failed the frozen Interviews matrix gate `a11y_copy_keys_present` (see `ops/KUWAIT_PILOT_DOCUMENT_JOURNEY_PRODUCTION_PROMOTE_FAILED.md`). Backend and employee-mobile artifacts were not the defect.

---

## Exact files and copy keys restored

**File changed (only):** `apps/wathefni-dashboard/src/lib/recruitingLifecycle.ts`  
**SHA256:** `09d5135fc0ec325b21858b191f49a58b58dae01e706271f013abecaa825f639e`  
**Source of wording:** exact strings extracted from production-green `/var/www/wathefni-dashboard/assets/dashboard-CfaEseRj.js` (sha256 `a6975562d73e7fede043cc55870fd2263f7935c293a644f2c83f4871f7e2a79a`). No regenerated translations from memory.

### Restored keys (EN + AR), including matrix-required a11y

| Key | English (exact) | Arabic (exact) |
|---|---|---|
| `interviewAgenda` | This week | هذا الأسبوع |
| `interviewAgendaDescription` | A practical week agenda for live interviews. Wathefni owns the schedule. | أجندة أسبوعية عملية للمقابلات المباشرة. وظفني يملك الجدولة. |
| `interviewTabUpcoming` | Upcoming | القادمة |
| `interviewTabVideo` | Video interviews | مقابلات الفيديو |
| `interviewTabNeedsFeedback` | Needs feedback | تحتاج ملاحظات |
| `interviewTabCompleted` | Completed | مكتملة |
| `interviewTabNoShow` | No-shows | عدم حضور |
| `interviewTabCancelled` | Cancelled | ملغاة |
| `interviewTabAll` | All | الكل |
| `interviewMetricUpcoming` | Upcoming interviews | مقابلات قادمة |
| `interviewMetricCompleted` | Completed | مكتملة |
| `interviewMetricNoShows` | No-shows | عدم حضور |
| `interviewMetricNeedFeedback` | Need feedback | تحتاج ملاحظات |
| `interviewMetricVideo` | Video interviews | مقابلات الفيديو |
| `interviewMetricFeedbackComplete` | Feedback complete | ملاحظات مكتملة |
| `interviewSearchPlaceholder` | Search candidate or email | ابحث عن مرشح أو بريد |
| `interviewRolePlaceholder` | Filter by role | تصفية حسب الوظيفة |
| `interviewPanelPlaceholder` | Panel / interviewer | اللجنة / المقابل |
| `interviewSearch` | Search | بحث |
| `interviewEmpty` | No interviews match this queue. Try another tab or clear the filters. | لا توجد مقابلات مطابقة. جرّب تبويباً آخر أو امسح عوامل التصفية. |
| `interviewShowing` | Showing {from}-{to} of {total} | عرض {from}-{to} من {total} |
| `interviewPrevious` | Previous | السابق |
| `interviewNext` | Next | التالي |
| `interviewNotesNotScorecard` | Free-text notes are not scorecards. Submit structured feedback separately. | الملاحظات النصية ليست بطاقة تقييم. أرسل الملاحظات المنظمة بشكل منفصل. |
| `interviewSyncStatus` | Calendar sync | مزامنة التقويم |
| `interviewProviderAccepted` | Provider accepted | قبول المزوّد |
| `interviewDeliveredProven` | Delivered (proven) | تم التسليم (مثبت) |

Pre-existing `interviewQueue` / `interviewQueueDescription` / `interviewStatus` left unchanged (already matched production).

**Not changed:** Interviews behavior, authority, scheduling, panels, feedback, scoring, calendar sync, permissions, or module boundaries.

---

## Exact document-journey changes retained

Unchanged from prior approved freeze (SHAs identical):

| File | SHA256 | Retained UX / API |
|---|---|---|
| `PostHire.tsx` | `e73d7027…` | HR reviewed / Reject (re-upload required) / Enter dates; PACI/MOI/PAM disclaimer; `residence` sensitive replace; renewal-safe wording |
| `api.ts` | `2b767b3b…` | `approve` / `reject` / `request_reupload` / `correct_metadata` review client |
| Journey backend + employee-mobile | as in freeze | Upload, renewal, dual-write, Art.18 vs national, versioning |

Built bundle proves: `HR reviewed`, `not PACI`, `residence`, `Enter dates`, `Mark as HR reviewed`, `Reject — re-upload`, plus restored interview a11y keys.

---

## Before / after dashboard artifact identities

| Role | Bundle | SHA256 |
|---|---|---|
| Production-green Interviews copy source | `dashboard-CfaEseRj.js` (`/var/www`) | `a6975562d73e7fede043cc55870fd2263f7935c293a644f2c83f4871f7e2a79a` |
| Failed staging-green (pre-recon) | `dashboard-CdJ5YPdj.js` | `dc8e8fb4523e7b20c7d31eff6d012cc50e4d193bbac4a25275f2feb365bf3113` |
| Reconciled staging dist (this pin) | `dashboard-Cibp23sm.js` | `c3562ee18f36e59367445e912739dc77ea1871e3c45081fb5109fa2a1137f085` |

Staging deploy path only: `/opt/wathefni/staging/dashboard-dist`. Production `/var/www` unchanged.

---

## New combined staging-green artifact SHA

`6018796d265c1a8d77e3bd880849b8e65f627003dc20ca544403db426d2097e1`

Pinned:

- `/opt/wathefni/staging/last-green.sha256`
- `/opt/wathefni/staging/kuwait-pilot-document-journey-artifact.sha256`
- Manifest: `/opt/wathefni/staging/kuwait-pilot-document-journey-manifest.txt`

Orchestrator-only pin unchanged: `e418227b0acb87a688c2f4b721497d3219179de111713292c68af2796885d915`.

---

## Full qualification results

| Suite | Result |
|---|---|
| Interviews staging matrix | **45/45** PASS (`a11y_copy_keys_present`, Arabic copy) |
| Document journey staging matrix | **68/68** PASS |
| Dashboard `npm test` | **49/49** PASS |
| Dashboard `tsc -b` + production build | PASS |
| Kuwait first-client foundation | **53/53** PASS |
| Offers/Hiring | **38/38** PASS |
| Optional-module-boundary | **301/301** PASS |
| Onboarding seeding smoke | **38/38** PASS |
| Compliance actions smoke | **31/31** PASS |
| Document upload smoke | **25/25** PASS |
| Document hub smoke | **18/18** PASS |
| Offer lifecycle / hire-override smokes | PASS |
| Candidates C3 staging | **49/49** PASS |
| Ranking R0–R3 staging | **57/57** PASS |
| Ranking result presentation | **213/213** PASS |
| Reports v1 | **80/80** PASS |
| Assistant A0–A3 (with service embedding env `voyage-4-large`) | **79/79** PASS |
| Assessments ON/OFF | **35/35** PASS |
| Employee capability smoke | GREEN |
| Employee `tsc --noEmit` | PASS |
| Staging health | **200** |
| Production health | **200** (untouched) |

---

## Production promotion plan (do not execute yet)

1. Owner approval of **exactly** `6018796d265c1a8d77e3bd880849b8e65f627003dc20ca544403db426d2097e1` (not `4be5298e…`).  
2. Production backup + documented rollback.  
3. Additive governed-document schema while foundation-green prod code runs (already proven safe).  
4. Surgical install of orchestrator journey bytes (unchanged from prior freeze) + **this** reconciled dashboard dist to `/var/www` only after backend health.  
5. Employee-mobile artifact matching freeze SHAs.  
6. Restart prod; re-run document-journey + Interviews **45/45** + frozen regressions (process-local dry_run).  
7. Residue sweep; pin production-green only if all pass.  
8. Do not claim PACI/MOI/PAM verification or automatic legal compliance.

---

## Owner next step

Approve production promotion of **exactly** `6018796d265c1a8d77e3bd880849b8e65f627003dc20ca544403db426d2097e1`.  
**Do not reuse** `4be5298e…`. **Do not deploy to production from this report alone.**
