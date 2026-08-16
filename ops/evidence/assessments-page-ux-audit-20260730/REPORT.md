# Assessments Page — Deep UX Audit (Pre-UI)

**Date:** 2026-07-30  
**Scope:** Assessments page only — **audit; no implement; no deploy**  
**Contract baseline:** `ops/evidence/assessments-queue-contract-20260730T163711Z` (**PASS** — preserve)  
**Canvas:** `assessments-page-ux-audit.canvas.tsx`

---

## Exact purpose

Assessments is the **HR ops desk** for assessment invitations and review:

| Tab | Purpose | Unit (locked) |
|---|---|---|
| **Send** | Who needs send / resend / delivery attention now | `assessments.cohort.*` — applications, latest attempt |
| **Attempts** | What invitations exist historically (incl. cancelled) | `assessments.attempt.*` — every attempt |
| **Reports** | Completed reports ready to read / mark reviewed | `assessments.review.*` — completed + review facet |

### Belongs here vs neighbors

| Surface | Owns | Does **not** own |
|---|---|---|
| **Assessments** | Send/resend/delivery queues; attempt history; report review; setup/authoring for eligible roles | Pipeline stages; ranking order; leadership CSV |
| **Candidates** | Application pipeline; open full application authority; cohort deep-links from “Open all in Candidates” | Send console / report viewer as primary desk |
| **Ranking** | Job-scoped advisory review order (CV-first) | Assessment send/review ops |
| **Overview** | Today’s work CTAs into assessment cohorts | Full queue desk |
| **Reports (nav)** | Metrics + CSV export | Day-to-day mark reviewed / view report |

**Preserve:** cohort / attempt / review predicates, assignment visibility, backend permissions, tenant isolation, `application_count`-only cohort badges.

---

## Current structure

### Top tabs
`Send` · `Attempts` · `Reports` (`AssessmentsPage.tsx`). Attempts stays highlighted for `needs_review`.

### Send
Cohort chips: Send · Resend · Delivery failed · In progress · Sent / pending.  
Rows: `SendRow` (application). Pagination: load-more 50 or “Open all in Candidates”.

### Attempts
“Recent attempts” or “Needs review”. Offset pagination. `AttemptRow` with View report / Mark reviewed / More / Open.

### Reports
Backend `status=completed` + `report_ready_count`. `ReportRow` → View report only.

### Metric strip
Seven tiles via `MetricGrid` (`xl:grid-cols-6`): Ready to send, Resend needed, Delivery failed, In progress, Completed, Needs review (clickable), Average score.  
Sent/pending is **not** on the strip. No `status_counts` fallback (contract PASS).

### Hierarchy
There are **no cohort cards** — only metric tiles + chips + dense table rows. Attempt and report rows are flat multi-column grids (`h-14`).

---

## Status vocabulary

| Label users see | Risk |
|---|---|
| Ready to send | Clear on metric + Send chip |
| Sent / pending vs “Sent” | Tab vs AttemptRow vs backend “Sent” diverge |
| In progress | Clear |
| Resend needed vs Resend vs Expired | Three names for expired/resend path |
| Delivery failed | Clear; raw delivery enums can leak via `stageLabel` |
| Completed | Clear |
| Needs review vs Review pending | Metric vs row badge wording differ |
| Expired | AttemptRow OK; no STAGE_LABELS entry (title-case fallback) |
| Cancelled | **Raw `cancelled`** on AttemptRow progressLabel |

`next_human_action` shown as snake_case with underscores → spaces (`send assessment`), not product copy.

---

## Actions / next steps

- Send primary is **tab/allowed_actions**-driven (`queuePrimaryAction`), not `next_human_action`.
- In progress primary is “Open” (view), not wait messaging.
- Cancelled: backend allows resend; UI More menu **omits** cancelled → action gap.
- Metric tiles (except Needs review) are non-interactive.
- Destructive cancel: `window.prompt` reason + confirm. Send/resend/review: confirm dialogs (EN-only).

---

## States

| State | Reality |
|---|---|
| Empty | Per-tab empty copy; module-off card exists |
| Loading | Suspense `PageSkeleton` on first load; no in-page skeleton; buttons use `busy` |
| Error | No Assessments-level `isError` banner |
| Stale | `keepPreviousData` on queries |
| Partial | Report may open with null presentation (“being prepared”) |
| Pagination | Send infinite; Attempts/Reports offset Previous/Next |

---

## Mobile / Arabic / RTL

- **No** `dir` on `AssessmentsPage` (Jobs / Interviews / Overview have it).
- Page chrome, metrics, tabs, rows, confirms: English hardcoded; `AttemptRow` voids `locale`.
- Dense fixed grids → horizontal scroll on narrow viewports.
- Report/workspace overlays set `dir` when locale is AR; list page does not.

---

## Drawer / modal

| Surface | Scroll lock | Focus / a11y |
|---|---|---|
| Attempt workspace | **No** body lock | No `aria-modal` / focus trap |
| Report modal | Overlay `overflow-y-auto`; page can scroll under | No focus trap |
| ConfirmDialog | No body lock observed | z-60 |

Interviews / CandidateProfile already implement body scroll lock — Assessments does not.

---

## Permissions / OCC / audit

- Module + `assessment.manage`; setup excludes recruiter / hiring_manager.
- Mark reviewed: `expected_updated_at` only (API also supports `expected_version` — unused).
- Send / resend / cancel: no OCC tokens.
- Review writes lifecycle audit event; UI has no assessment activity log beyond workspace timestamps.
- Cancel confirm is destructive; reason via native prompt.

---

## React Profiler proof

**Evidence gap (Critical for redesign gating):**

- No `React.Profiler` / `useProfiler` anywhere on Assessments.
- Only `dashboardPerfCountRequest('assessments'|'assessment-queue')` and `dashboardPerfMarkPageVisit('assessments')`.
- No interaction start / cached paint / network complete marks for tab, filter, queue open, or row click (Candidates list has those marks).

**No timings invented.**

---

## Findings ranked

### Critical

1. **No React Profiler / interaction perf proof** before UI redesign — cannot measure tab/filter/queue/row cost.

### High

1. **Arabic / RTL absent** on page chrome and rows.  
2. **Raw enums + snake_case next steps** (cancelled, delivery, workspace).  
3. **Status vocabulary collisions** (Resend needed / Resend / Expired; Sent variants; Needs review vs Review pending).  
4. **Drawer/modal missing body scroll lock and focus trap**.  
5. **Cancelled resend action gap** vs backend `allowed_actions`.

### Medium

1. Metric strip **duplicates** Send cohorts; mostly non-clickable; 7 tiles in 6-col grid; Average score on ops desk.  
2. Weak empty / loading / error truth.  
3. Dense multi-action rows — weak hierarchy.  
4. Cancel `window.prompt`.  
5. Mark reviewed OCC partial (`expected_version` unused).  
6. Send Open may miss attempt on current page.  
7. Authoring panel competes with daily ops on same page.

### Leave alone

- Locked `assessments.cohort.*` / `attempt.*` / `review.*` predicates and visibility.  
- Three-tab product model (polish, don’t merge authorities).  
- Cancelled never in Send cohorts.  
- Reports nav page vs in-page Reports tab separation.  
- Confirm dialogs for send/resend/cancel (replace prompt only).  
- `assessment.manage` + tenant isolation.  
- Presentation-only Send queue (no client row drop).

---

## Recommended visual direction

Match **Overview / Jobs / Interviews**:

- Warm cream surfaces (`#fffaf0` / `#f8f3e9`), strong near-black type (`#23211d`), muted secondary (`#716a5e`).
- Restrained color — one primary accent; danger only for delivery failed / cancel.
- Calm premium, less is more: **one mode → one queue → one primary action**.
- Demote or remove the metric wall; put counts on mode tabs / cohort chips.
- Row hierarchy: identity + status chip + one primary CTA; secondary under More.
- Drawers: cream panel, body scroll lock, focus trap — parity with Interviews.
- Localize status/action labels EN/AR before visual polish; add Profiler marks first.

**Suggested sequence (not started):** unify labels → demote metrics → RTL + drawer lock → Profiler baseline → warm cream visual pass.  
**Do not** reopen queue/count contracts.
