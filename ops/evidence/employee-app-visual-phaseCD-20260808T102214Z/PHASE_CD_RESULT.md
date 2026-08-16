# Employee App Visual Refinement — Phase C+D: Density, Hierarchy & Navigation Simplification

**Verdict: PASS** (local qualification; physical-device review not started, as instructed)

Phase A+B's trust, terminology, layout-token, safe-area, responsive-text,
accessibility and colour work is untouched. No regression against it was
reproduced, and its gates still run green in this phase's evidence.

---

## 1. Final Home hierarchy

Home now answers three questions in order, and nothing else.

| Order | Section | What it is | Notes |
|---|---|---|---|
| Header | Wordmark · unread bell · avatar | Inbox entry point | Bell carries the unread numeral and speaks the count |
| 1 | Greeting | `EditorialHeading` | Unchanged |
| 2 | **Today at work** | Shift time as the headline, attendance status beneath | One sky card. The workday is `font.h1`; the label is a small section title above it |
| 3 | **Tasks** | Onboarding progress card (when active) + compact task rows | Server-owned tasks only |
| 4 | **Destinations** | Compact rows for entitled modules that have no tab | Currently Documents only, in a full-suite company |
| 5 | Request leave | One `PremiumButton` | Only when the `leave.request` action is granted |

**Duplication removed**

| Was | Now |
|---|---|
| Leave tab + Leave destination card + Request-leave button | Leave tab + Request-leave button. Browsing leave and requesting leave are different jobs; a card that only reopens the tab was a third route to the same place |
| Schedule tab + Schedule destination card | Schedule tab |
| Inbox tab + Home inbox strip | One bell in the Home header |
| Onboarding task row + onboarding progress card | One progress card. The `onboarding_documents` task is filtered out while the journey card is shown, because the card already carries both the count and the call to action |
| Payslips destination card | Payslips tab |

The rule is in the contract, not in the view:
`homeDestinations = homeTiles − TABBED_MODULE_SURFACES`. Home cannot grow a
second route to a tab without changing `employeeAppComposition.ts`.

**Sparse companies.** A zero-module company gets a header, a greeting, and
whatever the server projects — no destination section, no filler. A leave-only
company gets a Leave tab and a request button, and no destination section at all
(the tab is the destination). A documents-only company gets exactly one
destination row. Every section renders only when it has real content.

---

## 2. Final bottom-navigation composition behaviour

**Home · Schedule · Leave · Payslips · Profile.**

- Home and Profile are the shell and always present.
- Schedule appears on either Shifts **or** Attendance.
- Leave and Payslips appear on their own entitlement.
- An unentitled tab is removed (`href: null`), not disabled — no dead slot, and a
  two-module company reads as a two-module app rather than a broken five-tab one.

**Inbox** moved out of the tab bar to a bell in the Home header:

- canonical route is now `/notifications`, declared once as `INBOX_ROUTE` and
  reused by the bell, the route registry and push follow-through;
- `/(tabs)/notifications` is kept as an **explicit alias**, so links already in
  flight (push payloads, older notifications) still land on the Inbox rather than
  falling back to Home;
- it is a pushed screen, so it has a real back control that returns to Home when
  there is no history;
- unread is a numeral in a badge *and* a spoken count in the accessibility label,
  so the state never depends on colour alone;
- Inbox remains `core`, reachable with zero entitlements.

No second composition system was created. `employeeAppComposition.ts` gained
`TABBED_MODULE_SURFACES`, `tabs.payslips` and `inboxEntry`, and lost `tabs.inbox`.

---

## 3. Page-by-page density changes

**Compact list primitive** — `src/components/lists.tsx`, modelled on Schedule's
`RecordedRow`: `ListRow` (surface background, strong title, quiet subtitle/meta,
opt-in icon tile, opt-in unread dot, opt-in semantic edge), `SectionHeader`
(optional count and disclosure), `ShowMoreButton`, and `usePagedList`.

Card treatment is now reserved for: something requiring action, the current state
of a module, or a problem.

| Screen | Before | After |
|---|---|---|
| **Home** | Pastel destination cards, inbox strip, two onboarding surfaces | Compact rows for tasks and destinations; one sky card for the workday; one lilac card for onboarding progress |
| **Documents** | One card per item in all three sections | **Needs attention** keeps a card with a semantic edge; **Current** is compact rows; **History** is year groups of compact rows, newest year open, older years closed, paged inside a year |
| **Inbox** | Feature cards | Compact message rows: unread dot, title, two-line preview, relative time. Unread first, then Earlier, then a collapsed *Account activity* group |
| **Leave** | One 130pt card per balance, cards per request | One olive card holding all balances as rows; requests are compact rows with type, dates and a status chip; single-day requests render one date |
| **Payslips** | A butter card per historical payslip | Detail keeps net pay as the headline; history is year groups of compact rows, current year open, paged inside a year |
| **Bank** | Verified, payroll-effective and submitted each got a full card, often printing the same masked IBAN three times | One butter card answering "where your salary goes"; one status line for what happens next; the confirmed account appears separately **only** when it differs from the account payroll is using; the submitted card appears only while the change is still pending; masking and encryption notes are footnotes |
| **Onboarding** | A completion card and a progress card saying the same thing | One lilac card: state chip, count, bar, next action. HR-owned items are **named** in compact rows with a status, instead of "your company is handling 3 items". Completed items are a collapsed record |
| **Profile** | Hero with name + job title, then Personal repeating the name and Employment repeating the job title | Hero owns identity. Personal is phone and email. Employment is department, start date, manager. No page heading/subtitle above the hero |

**Restraint.** `PastelCard` budgets are now enforced per screen by the static
gate (Home ≤ 4, Documents ≤ 3, Inbox+Leave ≤ 2, Payslips ≤ 3, Bank ≤ 4,
Onboarding ≤ 6, Profile ≤ 2). `WathefniBloom` survives only on genuine empty and
not-found moments. `IconBadge` is not applied by the shared row — a row asks for
an icon or gets none. Cream, surface and ink dominate; ambient tone appears as a
32pt icon tile or one card per screen.

---

## 4. List scalability approach

Employee history grows for as long as the employment does, so every growth list
is bounded the same way, and none of them nests a virtualized list inside the
page scroller (which trades a slow screen for a broken one):

1. **Group by calendar year** where the data has dates — Documents history,
   Payslip history. Newest year first; entries with no usable date sort last
   under a null year rather than being dropped or guessed into the present.
2. **Collapse all but the most recent group** on arrival.
3. **Page inside a group** with `usePagedList`: Documents 10, Payslips 12,
   Inbox 15, Leave 12 per page, grown by an explicit "Show N more".
4. **Partition by relevance** where grouping by year would not help — the Inbox
   splits Unread / Earlier / Account activity, and the activity group is
   collapsed, so repeated activation and device messages cannot push weeks of
   real HR mail off the first screen. Unread is never demoted regardless of flow,
   and an unrecognised backend flow is treated as real HR mail.

Proven against a fixture of 264 documents across 11 years and against long inbox
and payslip histories. Schedule's already-capped recent history is unchanged and
remains the model.

---

## 5. Owner decisions still unresolved

1. **Payslips as a permanent tab.** It takes the slot Inbox vacated. For a
   company that has payroll but where employees open a payslip once a month, a
   Documents tab might earn the slot instead. Needs a look on a real device with
   a real company before it is settled.
2. **"Account activity" as the label** for activation/device/session messages.
   It is accurate and non-technical, but it is a category we named; HR may have a
   word they prefer.
3. **Undated history grouping.** Undated documents and payslips currently sort
   last under an "Undated" heading. Whether that is better than hiding them is a
   judgement about how often the backend leaves the date empty in production.
4. **Human employee number in Profile.** Still absent: `/app/profile` exposes
   only `company_code` and `employee_key`, which are backend keys, not a staff
   number an employee could quote. It needs a real canonical field before a row
   can exist.
5. **Documents has no tab** and is reachable only from Home. That is deliberate
   (it is the one module without one), but for a compliance-heavy company it may
   be the most-visited screen.

---

## 6. Qualification

All local gates green — see `local-gates.txt` in this directory.

| Gate | Result |
|---|---|
| typecheck (`tsc --noEmit`) | PASS, 0 errors |
| typecheck strict-unused | PASS |
| **density + hierarchy (behavioural, new)** | PASS, 24 checks |
| **density + hierarchy static scan (new)** | PASS, 71 checks |
| composition shapes | PASS, 61 checks (was 54; +7 for the nav change) |
| push follow-through | PASS, 14 checks |
| documents hierarchy | PASS, 7 checks |
| feature-unavailable copy | PASS, 9 checks |
| capability foundation | GREEN |
| colour system (A+B) | PASS, 32 checks |
| a11y + i18n static scan | PASS, 21 checks |
| session / refresh static proof | PASS, 8 checks |
| PIN crypto selftest | PASS |
| iOS bundle export | PASS, 1368 modules, 0 errors |

EN/AR keysets are identical and every `t()` key used in the app resolves in both.
New keys this phase: `common.showMore`, `tabs.payslips`, `time.*` (5),
`notifications.systemActivity`, `documents.historyUndated`,
`payslips.undatedPeriod`.

Two existing gates were updated rather than worked around, because the truth they
asserted changed: the Inbox path moved, and Home destinations are no longer a
mirror of the entitlement tiles. Both now read the path from the contract instead
of restating it, so the next move cannot pass a stale test.

---

## 7. Remaining items for the next High-Value Additions phase

Deliberately **not** started here, per the scope guard:

1. Certificates (employment letter / salary certificate request).
2. Announcements.
3. Shift acknowledgement.
4. Leave edit workflow (cancel exists; edit does not).
5. HR App.
6. Auth Wave 2 Phase 6.

Carried forward from this phase as candidate work:

7. **Documents upload from Home.** The renewal task routes to Documents; the
   employee still has to find the item. A direct route is an addition, not a
   density fix.
8. **Inbox read-all / filter.** With the activity group collapsed the pressure is
   lower, but a long unread list still has no bulk action.
9. **Payslip year total.** The year header shows a count; a net total for the
   year is the obvious next question and needs payroll to own the number.
10. **Bank change history.** The screen now shows one account and one status; an
    employee who changed banks twice cannot see that. Needs a contract field.
11. **Physical-device qualification** — EN/AR, LTR/RTL, AX3/AX5 Dynamic Type,
    small-screen (SE) and large-screen, VoiceOver over the new rows, bell badge,
    and the collapsed groups. Checklist in `PHYSICAL_QA_CHECKLIST.md`.

The Employee App is **not** frozen.
