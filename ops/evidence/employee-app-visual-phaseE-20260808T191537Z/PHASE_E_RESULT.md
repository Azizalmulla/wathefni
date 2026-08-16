# Employee App Visual Refinement — Phase E: High-Value Employee Additions

**Verdict: PASS**
**PHYSICAL_VISUAL_QA_READY = YES**

Six additions shipped. Every one is a read of information a backend module
already owned; none introduces a rule, a threshold, or a calculation the product
did not already have.

---

## The defect this phase found first

Before adding anything, the canonical audit compared what `/app/leave` emits
against what the app reads. They did not match.

The server has always sent `current_balance`, `entitlement_days`,
`accrued_to_date`, `consumed`, `available` and `reserved`. The mobile
`LeaveBalance` type declared `balance_days`, `accrued_days`, `consumed_days` and
`period_year` — four names the API has never sent. The Leave tab rendered
`formatNumber(balance.balance_days ?? 0, locale)`.

So for any company with balances switched on, every leave type read **0 days
available**. Not blank, not an error — a confident zero, under a heading the
employee would reasonably trust, on the screen they check before asking for time
off.

This is a real regression under a phase that is otherwise frozen, and it is the
exact failure mode Phase E is meant to prevent, so it was fixed here rather than
deferred. The contract now names only fields the server sends, and a missing
number renders as nothing.

---

## Additions shipped

### 1. Request Leave — balance before submission

The relevant balance for the **selected leave type** now appears in the request
flow, above the reason field.

- Source: `GET /app/leave` → `balances[]`, via the same `['leave']` query key the
  Leave tab uses, so opening the form costs no extra request and cannot disagree
  with the tab behind it.
- `available` (pending requests already deducted) is preferred over
  `current_balance` when the company tracks reservations; the distinction is the
  server's and is carried through rather than averaged.
- `can_take_from` is surfaced when the balance exists but is not yet takeable —
  a balance the employee cannot use is worse than no balance if presented as
  available.
- The server reports balances as `observe_only`, `balances_enforced: false`,
  `balances_binding: false`. The app therefore states the balance as information
  and keeps the non-enforcement note. It does not present it as an allowance
  being spent down.
- **Absent means silent.** Balances off, no row for that type, or a non-numeric
  value all render nothing. A genuine `0` still renders, because that is a fact.

### 2. Request Leave — requested duration

Once dates are selected: **"You're requesting 3 working days."**

The number is not counted on the device. It cannot be: the weekend is company
policy (`leave_policies.weekend_days`) and the public holidays are company data
(`public_holidays`), and neither is on the phone. A local calendar-day count
would tell an employee taking Thursday to Monday that they are requesting five
days when the company will charge three.

New thin read: **`GET /app/leave/duration`**. It composes exactly the primitives
the create path already uses, in the same order, with the same fallbacks —
`get_leave_policy` → `holiday_dates_for_range` → `chargeable_leave_days` — so it
can only ever agree with what a submitted request is charged. It writes nothing,
reserves nothing, and is gated on the same `leave/request` permission as
submitting, so company rest days are not readable by someone who cannot request
leave.

Abstention is explicit: an invalid range, an unavailable leave type, or any
failure returns `available: false`, and the app shows no line at all. A range
containing no working days says so rather than displaying `0`.

### 3. Manager contact

The Profile manager row shows the manager's name, their number beneath it, and a
call button.

- Source: `GET /app/profile` → `employment.manager.{name, phone}`, populated only
  when a manager phone is already stored on the employee's own record.
- Nothing new is exposed: this number was already printed on this screen. The
  button only saves copying it out.
- The action appears **only** when the stored digits form a dialable number.
  Kuwait 8-digit numbers are normalised to `+965…` so they dial while roaming; an
  unrecognised shape yields no button rather than a `tel:` link that dials a
  stranger.
- Dialling is a discrete 44×44 control, not a tap target on the whole row — a row
  that dials when brushed is a row nobody scrolls past safely.
- No chat, no WhatsApp, no third-party channel. See *Owner decisions* below.

### 4. Inbox relative time

Rows read "Just now", "12 min ago", "2h ago", "Yesterday", falling back to a
localized date for older messages, in EN and AR.

This existed after Phase C+D; Phase E corrected the wording to the requested
phrasing and closed the honesty gap: relative time **rounds**, so the exact
Kuwait-time timestamp the server sent is now attached to the row's accessibility
label rather than being replaced by the approximation.

### 5. Payslips — multi-year grouping

Verified end to end: grouped by year, most recent year open on arrival, older
years collapsed, each year paged at `PAYSLIP_PAGE`, net pay unchanged in
prominence, released-only authority untouched. No search or filter chrome was
added for a 12-per-year dataset.

One dead end closed: a company with a single year of payslips was still given a
collapsible year header, so the only gesture available was to collapse the screen
into nothing. A lone year now keeps its heading — "2026" is still worth stating —
but is no longer collapsible. The same fix was applied to Documents history for
consistency.

### 6. Document expiry task prominence

Home now reads **"Civil ID expires in 18 days"** instead of a generic renewal
label.

`GET /app/home` already loaded the compliance rows to count renewals, then
discarded everything except the count. The soonest renewal's `document_type`,
localized `label`, `expiry_date` and `review_status` now ride along on the task
as `detail`.

This decides nothing. `renewal_required` remains the documents module's verdict;
the server picks a row and passes its stored values through, computing no
deadline. Rows the module left undated sort last and contribute no date, so an
expiry can never be inferred from a document that has none.

The day count is rendered from the canonical `expiry_date` against today's
**Kuwait** date, compared as calendar dates — a document does not expire at a
different hour depending on where the employee is standing. No detail, or a date
that will not parse, falls back to the generic label; urgency that cannot be
substantiated is never implied. Expired and expires-today have their own copy
rather than a negative or zero day count.

Home → Documents remains the pattern. No expiry dashboard was added, and Home
still does not re-query the documents module.

---

## Exact canonical sources used

| Addition | Endpoint | Fields | Owning authority |
|---|---|---|---|
| Leave balance | `GET /app/leave` | `balances_enabled`, `balances[].current_balance`, `.available`, `.reserved`, `.can_take_from`, `balances_enforced`, `balances_binding` | `leave_balances` rollup of the `leave_ledger` |
| Requested duration | `GET /app/leave/duration` *(new, read-only)* | `available`, `chargeable_days`, `basis` | `chargeable_leave_days` + `leave_policies.weekend_days` + `public_holidays` |
| Manager contact | `GET /app/profile` | `employment.manager.name`, `.phone` | `employees` roster, matched on stored `manager_phone` |
| Inbox time | `GET /app/notifications` | `created_at` | notifications module |
| Payslip years | `GET /app/payslips` | `period_start`, `period_end`, `net`, `currency` | Payroll Wave 3 released payslips |
| Document expiry | `GET /app/home` → `tasks[].detail` *(new field)* | `document_type`, `label`, `expiry_date`, `review_status` | `list_employee_compliance_journey` |

**Backend surface changed:** two read-only exposures in
`wathefni-orchestrator/app.py` — the `/app/leave/duration` endpoint and the
`detail` field on the existing `document_renewal` task. No write path, schema,
lifecycle, or decision rule was modified.

---

## Employee number — domain-model gap (not filled)

`/app/profile` exposes `employee_key` and `company_code`, which are backend keys,
and no human-facing staff number. The raw key was **not** restored and nothing
was invented in its place.

The gap is real and has a real home: `employee_persons.employee_number` exists in
the Wave 2 employee hub but is not joined into the profile projection. Wiring it
is not a display change — it needs the hub to be authoritative for the roster and
the number to be populated and stable per tenant, which is a domain decision, not
a mobile one. Recorded for a later phase.

---

## Deferred, as instructed

Salary/employment certificate requests · company announcements · shift
acknowledgement · leave-edit workflow · YTD earnings · chat · clock in/out ·
attendance disputes · editable employment profile · org chart/directory ·
Payments/WPS.

All eleven are asserted absent by the static gate rather than merely left
undone, so a later change cannot reintroduce one silently. Certificates remain
the highest-value future candidate and need a cross-app design with HR-side
issuance.

## Owner decisions still open

1. **WhatsApp to manager.** The stored manager number is a canonical Kuwait
   mobile, so a `wa.me` link would work and matches local workplace norms. Not
   shipped: the brief prefers native actions, and a second button on the row
   costs more than it returns. One decision, easily added.
2. **Balance semantics.** `available` and `current_balance` are labelled
   identically to the employee. If a company enables reservations, "you have 16
   days" will mean *after* pending requests without saying so. Worth a copy
   decision before balances are switched on for a real tenant.

---

## Qualification

| Requirement | Result |
|---|---|
| Request Leave shows canonical balance when valid | PASS |
| Requested-day count uses company/workday logic | PASS — server-side, same primitives as create |
| Unavailable balances/durations never become invented facts | PASS — and one live case of this fixed |
| Manager contact uses canonical authorized data | PASS |
| Inbox relative time EN/AR correct | PASS — exact timestamp preserved |
| Payslips scalable across multiple years | PASS |
| Document expiry task uses canonical expiry data | PASS |
| Navigation from Phase C+D unchanged | PASS — tabs, Inbox bell, Documents routing |
| No raw employee key returns | PASS |
| No new business authority created | PASS |
| EN/AR parity | PASS — identical keysets, matching placeholders |
| TypeScript clean | PASS — `tsc --noEmit --noUnusedLocals` |
| Phase 0–4 + Visual A–D regressions green | PASS |

**Gates:** 23 behavioural (mobile) · 79 static (mobile) · 34 backend · 11 prior
suites re-run · iOS bundle exported clean (3.24 MB).

`smoke-test-leave-guardrails.py` cannot run locally — it imports `app.py`, which
requires `psycopg2`. Pre-existing environment limitation, unrelated to this
phase; it runs on staging.

## Not claimed

This is static and behavioural qualification. No physical iPhone review was
performed. Dynamic Type at AX3/AX5, RTL rendering on device, the call sheet
actually opening the dialler, and the new Request Leave summary block at small
widths all still need eyes on hardware.
