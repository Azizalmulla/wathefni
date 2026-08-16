# HR Hiring Home + Interviews — physical-surface qualification

Stamp: `20260810T173000Z`  
Surfaces: `/hr/hiring` · `/hr/candidates` (list) · `/hr/interviews` · `/hr/interviews/[id]`  
Actor: Aziz owner `96599338566`  
Mode: **audit only — no redesign shipped**

## Functional verdict: **CONDITIONAL — do not lock yet**

Hiring home is cream and capability-gated with correct safe-back parents. Interviews list/detail exist and Hiring upcoming can deep-link to real interview IDs. **Neither surface is honesty-complete:** Candidates browse/ranking is still unscoped (empty success on client), and interview notes save is broken against concurrency tokens. Freeze Hiring and Interviews **together** after one honesty + cream-list wave — not separately.

---

## Entry → destination map (live)

| Entry | Lands on | Honest? |
| --- | --- | --- |
| Hiring tab | `/hr/hiring` | Yes |
| Priority `prehire_*` (follow-up / ready / assessment / role) | `/hr/candidates` (unscoped list) | **No** — empty ranked list; no position; no filter for the priority kind |
| Priority `candidate_decisions` | `/hr/candidates/{app_key}` | Yes when items exist; **empty today** because rankings called without position |
| Upcoming interview / feedback | `/hr/interviews/{interview_id}` | Yes (live) |
| Upcoming offerish candidate | `/hr/candidates/{app_key}` | Yes |
| Browse Jobs | `/hr/candidates` | **Weak** — no Jobs/positions surface |
| Browse Candidates | `/hr/candidates` | **No** without position |
| Browse Ranking | `/hr/candidates` | **No** without position |
| Browse Assessments | `/hr/candidates` | **Weak** — Assessments capability remapped to rankings list |
| Browse Interviews | `/hr/interviews` | Yes |
| Assistant `ranking` | `/hr/candidates` | Same list honesty gap |
| Assistant `jobs` / `assessments` | blocked (web-only) | Honest block — **asymmetric** vs Hiring browse |
| Assistant `interviews` + `app_key` | `/hr/interviews/{app_key}` | **Broken** — app_key ≠ interview UUID |
| Candidate `schedule_interview` | `/hr/interviews` list | Dead/misleading if button ever appears (action not mobile-executable) |

Live probe priorities (Aziz): prehire totals follow-up=2, ready=7, assessment=2, role HR; `candidate_decisions` total **0**. Unscoped rankings: `requires_position=true`. Scoped `position=HR`: total 3 / 2 items. Interviews: 4 rows (completed/cancelled Hamad). Open positions available: 9.

---

## Jobs / Ranking / Assessments remap — still right?

**Interim remap is acceptable only if Candidates becomes an honest position-scoped ranking entry.**

| Remap | Judgment |
| --- | --- |
| Ranking → Candidates | **Keep**, but Candidates must require/select a job and surface `requires_position` |
| Jobs → Candidates | **Not right long-term** — `/dashboard/mobile/positions` exists (9 open). Prefer Jobs → positions browse, or drop Jobs browse until then |
| Assessments → Candidates | **Not right** — false promise; prefer hide browse row, or web-only / dedicated assessment queue later. Do **not** invent assessment workflow on mobile in this wave |

No workflow expansion required beyond making the **current** Ranking/Candidates path honest (position scope + honesty flags).

---

## Position-scoped ranking — how it should work

**Today**
1. Backend ranking authority requires exact `position` (`job_required`).
2. Mobile `GET /candidates` with empty position now returns honest flags (`ranking_unavailable`, `requires_position`) — Candidate freeze.
3. Client `mobileApi.candidates` never sends `position`; `normalize.collection` **drops** honesty flags → UI shows empty “Ranked pipeline”.
4. There is **no** HR role picker / job entry before ranking. Positions API unused by mobile.

**Honest presentation (minimal, no parallel list)**
1. Hiring browse Ranking/Candidates (and priority→list) open Candidates **with a position required**.
2. If no position: show localized empty/requires-position state (“Choose a job to rank candidates”) — not an empty ranked pipeline.
3. Role selection: pick from `GET /dashboard/mobile/positions` (existing), or carry `position_code` from Hiring priority `prehire_role_priority` / role destination when present.
4. Pass `?position=` into rankings; preserve backend job scope. Do not invent company-wide unscoped list.

---

## Interviews — list / detail / notes

| Check | Result |
| --- | --- |
| List truth | 4 live interviews; destinations `/interviews/{uuid}`; actions include `read`/`write` even on cancelled/completed |
| Detail truth | Facts present; `updated_at` on DTO; **`notes_version` not on mobile DTO** |
| Notes spine | **Direct POST** (not SOD) — intentional vs Leave/Candidate |
| Notes without token | **FAIL** `missing_expected_version` (proven) |
| Mobile request model | `InterviewNotesRequest` has notes/status/generate_summary only — **no expected_* fields** |
| Notes error UX | Mutation error replaces entire detail panel |
| Save side effect | `save_notes_only` can move `scheduled` → `completed` |
| Cache | Invalidates `['interview', id]` only — not list / Hiring upcoming |
| Schedule continuity | Hiring→detail OK; Candidate→list only; Assistant app_key→UUID crash |

---

## Cross-cutting

| Area | Result |
| --- | --- |
| RBAC / entitlements | Hiring tab + browse gated; interview notes need `interview_notes` write + `interview.manage`; destinations use `destinationAvailable` |
| Tenant isolation | Detail/list helpers scoped by company (unchanged) |
| EN/AR/RTL | `hrHiring.*` EN+AR OK; upcoming kind labels EN-hardcoded in composition; priority summaries server EN; Interviews chrome in `src/hr/i18n` EN+AR |
| Safe-back / cold-start | `/hr/hiring`→`/hr`; lists→Hiring; details→lists — **PASS** |
| Visual | Hiring home **cream**; Candidates list + Interviews list/detail **legacy** `@hr/theme` Screen/WorkspaceHeader |

---

## Functional blockers (must fix before freeze)

1. **Interview notes save broken** — mobile omits concurrency tokens; server requires them (`missing_expected_version`).
2. **Candidates list fake empty** — unscoped call + dropped `requires_position` / `ranking_unavailable`.
3. **Assistant interview deep-link** uses `app_key` as `interview_id` → UUID error / not found.

## Honesty gaps (block lock; smaller than above)

4. Jobs / Assessments browse labels remapped to Candidates (false product promise).
5. Priority cards land on unscoped Candidates (not filtered by ready/follow-up/assessment).
6. Hiring upcoming EN hardcodes (`Interview` / `Feedback due` / `Offer`).
7. Priority body = raw status underscores; titles EN from server.
8. Candidate `schedule_interview` → unfiltered list (misleading if ever advertised).
9. Notes error blanks whole detail; list/Hiring caches not invalidated on notes save.
10. Write still advertised on cancelled/completed interviews (capability vs presentation).

## Exact visual migration needed (no redesign)

Map Candidates list + Interviews list/detail onto cream HR system (Attendance/Leave/Candidate detail pattern):

1. Replace `@hr/theme` `Screen`/`WorkspaceHeader` with cream `PageScreen` + `HrPushedNav`.
2. One cream surface hierarchy; demote multi-tone lilac/cream card stack in `OperationalDetailView` / list rows toward shared ListRow/SectionHeader/StatusChip.
3. Hiring home already cream — keep; only align list/detail siblings.
4. Present requires-position / ranking-unavailable as calm empty state (not plum error chrome).
5. Notes editor: cream input + inline error (don’t replace whole page).

## Freeze together?

**Yes — freeze Hiring home + Interviews as one wave after the blockers above.**

Shared seams: same recruiting capabilities, Hiring upcoming→interview detail, safe-back parent Hiring, Candidates list used by Hiring browse/priorities, cream continuity. Freezing Hiring cream alone while Interviews notes are broken and Candidates list is dishonest would stamp a false PASS.

**Out of scope for lock wave (debt):** full Jobs positions browser, Assessments mobile queue, SOD for interview notes, schedule/reschedule/cancel on mobile, inventing schedule-from-candidate workflow.

## Lock criteria (Hiring + Interviews)

- [ ] Position-scoped Candidates path + surface `requires_position` EN/AR
- [ ] Interview notes pass expected version/updated_at; stale/error inline; invalidate list/Hiring
- [ ] Assistant interview deep-link uses interview_id (or list only)
- [ ] Browse honesty: Ranking/Candidates OK with position; Jobs/Assessments remapped or relabeled honestly
- [ ] Cream migration for Candidates list + Interviews list/detail
- [ ] Upcoming kind labels EN/AR
- [ ] One physical EN+AR pass
- [ ] Then stamp PASS and freeze both

Evidence: this folder (`qualify-run.txt`, `notes-concurrency-probe.txt`, `client-gap-scan.txt`).
