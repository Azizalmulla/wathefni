# Overview End-to-End Action Audit

**Date:** 2026-07-28 (Asia/Kuwait)  
**Scope:** Read-only. No UI, counts, filters, ranking, lifecycle, or data changes.  
**Company audited live:** `WATHEFNI` on `root@76.13.63.68` (`wathefni-orchestrator` @ `:8010`)  
**Primary modules:** `apps/wathefni-dashboard` Overview (`App.tsx`), `wathefni-orchestrator/prehire_overview.py` (**production copy**), Candidates list aggregation, Ranking (`candidate_ranking.py` + Ranking page)

**Authority note:** Production `prehire_overview.py` differs from the local workspace copy. This audit treats **production** as the runtime source of truth.

---

## Final verdict

**FAIL — Overview experience**

Overview is useful as a pressure board, but several headline numbers, labels, and CTAs promise **people** or **completed ranking decisions** while the system actually counts **applications × overlapping action signals**, routes to **partial destinations**, and lands Ranking in a **manual, score-null, schema-mismatched** state. The mismatches are mostly **systemic**, not one-off data bugs.

---

## Live snapshot (WATHEFNI, 2026-07-27 ~22:15 UTC)

| Signal | Overview claim | Record type actually counted | Distinct phones (people) | Apps |
|---|---|---|---:|---:|
| Follow up with candidates | **4** | applications with failed outbound delivery | **2** | 4 |
| Review ready candidates | **3** | applications in ready statuses | **3** | 3 |
| Send pending assessments | **3** | applications with assigned assessment in `pending`/`in_progress`/`expired` | **2** | 3 |
| Prioritize role card value | **Accounting Excel — 3** | sum of role `follow+ready+assess` signal counters | **1** app / **1** person | 1 |
| Top priorities queue | **14 actions** | work-queue rows = `(action_type × app_key)` | repeated names | 14 rows |
| Suggested next action | Follow-up (winner) | same follow-up application cohort | 2 people / 4 apps | — |

Role winner:

```text
ACCOUNTING_EXCEL / Accounting Excel
ready=1, follow=1, assess=1, active=1
attention card value = 1+1+1 = 3
```

That single application (`96597485758-WATHEFNI-ACCOUNTING_EXCEL`, Hamad Almulla) matches **all three** predicates at once.

---

## Section-by-section audit

### 1) Suggested next action (hero)

| Check | Finding |
|---|---|
| Claim | Highest-priority hiring action + reason + primary CTA |
| Record type | Depends on winner: applications (follow/ready/assess/interview) or role pressure |
| Backend authority | `prehire_overview.compute_next_action` via `build_overview_authority` → `/dashboard/prehire/summary` |
| Click | `onOpenDestination(nextAction.destination)` |
| Destination honesty | **Partial.** Follow-up/ready/assess destinations set Candidates filters correctly. Interview destination drops filters. Role destination opens Ranking with position set but **does not run ranking**. |
| Filters preserved in URL | **No.** URL only stores `page` (+ optional `candidate`). Refresh/Back lose Overview filters. |
| Actionable without extra steps | Follow-up/ready: list is filtered, but person aggregation still required. Role: **extra Rank click required**. |

Live winner at audit time: `follow_up_failed_delivery` / `total_matching=4` / destination `{page:candidates, filters:{follow_up:needed}}`.

**Layer:** backend priority (ok) + frontend routing (interview/ranking incomplete) + presentation (says “candidates”, counts applications).

---

### 2) What needs attention today — four ActionCards

#### A. Review ready candidates = 3

1. **Claim:** “N candidates ready for an HR decision.”
2. **Record type:** **applications** (`screening_complete`, `review_pending`, `ready_for_review`) with reviewable CV/production predicate.
3. **Authority:** `compute_action_counts.ready_for_review` (`COUNT(*) FILTER` on applications).
4. **Click:** `viewReadyForReviewCandidates` → Candidates with `review_status=ready`, `sort=ready_for_review`.
5. **Destination match:** Backend Candidates filter uses the same `ready_for_review_predicate`. **Application cohort matches.**
6. **People vs apps:** Live apps are 3 distinct phones → person list should show **3**. (If HR previously saw 2, that was not reproduced in this live cohort.)
7. **Duplicates:** Not accidental — one app per person here.
8. **Actionable:** Yes for review; still needs opening a profile to decide.
9. **Cross-page consistency:** Matches Candidates filter; Reports uses same overview counts. Ranking/Jobs are separate.

**Mismatch:** Label says **candidates/people**; number is **applications**. Today coincidently equal (3/3). **Systemic presentation/contract issue.**

#### B. Send pending assessments = 3

1. **Claim:** “N candidates are ready for assessment” / CTA “Send pending assessments”.
2. **Record type (production):** applications already **assigned** with assessment status in `pending|in_progress|expired` (plus delivery-failed open attempts). Empty/unassigned does **not** count.
3. **Authority:** `assessment_pending_predicate` in production `prehire_overview.py`.
4. **Click:** Candidates with `assessment_status=awaiting` (same predicate).
5. **Destination match for list:** App cohort matches Overview count (**3 apps / 2 people**).
6. **Real send action:** **Weak.** Overview does **not** open Assessments. Assessments page `assessmentQueue()` only treats `''|pending` (not `expired`) as sendable. Live cohort is mostly **`expired`** with stale `raw_json.assessment.status=pending` — needs **resend**, not first send.
7. **Duplicates:** Same people across HR + Accounting Excel apps (real multi-application), not accidental list bugs.
8. **Cross-page consistency:** Overview/Candidates awaiting filter agree; Assessments “Pending assessments / Send” queue uses a **different frontend rule**.

**Mismatch:** Copy promises “send to candidates ready for assessment”; authority is “assigned assessment attention (incl. expired)”. Destination is Candidates, not the Assessments send/resend surface. **Systemic (backend definition + FE routing + label).**

#### C. Follow up with candidates = 4

1. **Claim:** “N candidates need HR follow-up.”
2. **Record type:** **applications** with failed/unrecovered `outbound_delivery_events`.
3. **Authority:** `follow_up_needed_exists` / `compute_action_counts.follow_up_needed`.
4. **Click:** Candidates `follow_up=needed`.
5. **Destination:** Same SQL predicate → **4 apps**.
6. **People after aggregation:** **2** (Hamad phone `96597485758` on ACCOUNTING_EXCEL+HR; Aziz phone `96598900677` on ACCOUNTING+HR).
7. **Duplicates:** Real separate applications per job for the same person.
8. **Actionable:** Filter is correct; action is still profile/outbound recovery, not one-click from Overview.
9. **Consistency:** Overview card ↔ Candidates filter agree on apps; Candidates **footer/list is person-first**, so HR sees ~2 rows for a “4” card.

**Mismatch:** **4 apps vs 2 people.** Layer: **backend count (applications) + frontend person aggregation + presentation language (“candidates”). Systemic.**

#### D. Prioritize by role / Accounting Excel = 3

1. **Claim:** Role needs attention; value badge shows **3**.
2. **Record type:** **Not people, not apps, not completed ranks.** It is `follow_up_count + ready_count + assessment_pending_count` for the winning role — **overlapping signal sum**.
3. **Authority:** `compute_role_priority` then FE `roleAttentionValue`.
4. **Click:** `viewRolePriority` → Ranking page, `rankPosition=ACCOUNTING_EXCEL`.
5. **Destination:** Ranking pool for that job is **1 application / 1 candidate**. Completed runs exist (`pool_total=1`), but UI starts empty until **Rank**.
6. **Why Overview says 3 and Ranking shows 1:** One application contributes 1+1+1 signals. Ranking correctly counts the job pool (**applications for that position**), not the summed attention score.
7. **Is Overview based on a completed ranking result?** **No.** Role priority is SLA/signal pressure only. Ranking is a separate on-demand job pool score.
8. **Actionable:** No — requires Rank click; then score/presentation still contradictory (below).

**Mismatch:** Card value ≠ candidate count ≠ ranking result. **Systemic aggregation + destination contract.**

---

### 3) Top priorities (+ View all)

| Check | Finding |
|---|---|
| Claim | “Specific people to contact or decide on next” + “N actions” |
| Record type | Work-queue **actions** keyed by `(action_type, app_key)` |
| Backend | `compute_work_queue` (follow, ready, assess, interview), already deduped by `(action_type, app_key)` |
| FE dedupe | `dedupeWorkQueueItems` — same key; preserves distinct actions and distinct apps for one person |
| Click row | Opens **candidate profile** by `app_key` (good). Destination filters on the item are ignored. |
| View all | Only expands local list beyond 5; **no full queue page** |
| Hamad / Aziz repeats | **Expected under current contract**, not accidental duplication: same person appears once per (action × application). Live: Hamad 5 rows, AZIZ 6, Aziz 2 |

**Mismatch:** Copy says people; rows are action×application. Repeated Hamad/Aziz is **real multi-app + multi-action**, poorly presented as “people”. **Systemic presentation + missing person-level rollup.**

---

### 4) Role next steps

| Check | Finding |
|---|---|
| Claim | Per-opening next step + “N active” badge |
| Record type | Jobs/`positions` inventory + application `stage_counts` / `active_count` |
| Source | `allPositionsForSelectors` (positions endpoint, limit 200), first **5** only |
| Click | Candidates filtered by `position` |
| 0 active / 1 active | Badge is honest for active applications; openings with **0 active** can still appear in the first five depending on inventory order |
| Consistency | Stage bottleneck label uses status histogram language (“review”, “screening”) that can disagree with Overview attention cards for the same role |

**Mismatch:** Not always the roles Overview just prioritized; not ranked by pressure. Can show quiet/0-active roles while Accounting Excel pressure lives in another card. **Frontend selection/aggregation.**

---

## Ranking deep audit (Accounting Excel)

### Observed behavior

1. Overview recommends / cards **Accounting Excel — 3**.
2. Ranking destination preselects `ACCOUNTING_EXCEL`.
3. HR must press **Rank** (`runRanking` only on button). No auto-fetch of latest `ranking_runs`.
4. Latest completed run (`2026-07-27 22:14:52Z`): `pool_total=1`, `scored_count=1`, app `96597485758-WATHEFNI-ACCOUNTING_EXCEL`.
5. Stored item:
   - `eligibility_bucket`: `insufficient_information`
   - `advisory_score`: **null**
   - `component_scores`: skills 22.5, semantic 7.61, experience 14.0, education 15.0 (non-zero)
   - `required_missing`: **`["ck_ranking_reader_failed:UndefinedFunction"]`**
   - `required_evidence_complete`: false
   - Narrative: positive (“Excel-ready accounting support…”) while eligibility remains insufficient
6. FE badge: `Math.round(null)` → **0 / 100**
7. Fit summary shows the positive narrative
8. “Top strengths” stringify evidence **values** (objects/arrays) → raw JSON / technical dumps
9. Evidence list uses raw field keys (`employment`, `cv_education`, …)
10. Score breakdown UI expects legacy keys (`role_fit`, `skill_match`, …) but API returns R0–R3 keys (`skills_alignment`, …) → **zeros / schema mismatch**
11. Risks always include generic “Human review is still required…” from legacy adapter

### Answers to the ranking questions

| Question | Answer |
|---|---|
| Why Overview `3` vs Ranking `1`? | Overview sums overlapping role signals; Ranking lists the job application pool (1). |
| Why press Rank after Overview recommends the role? | Destination only sets `rankPosition`; does not call `getRanking` / load latest run. |
| Why `0/100` with positive fit summary? | CK ranking reader failure nulls `advisory_score`; narrative still generated; FE coerces null→0. |
| Why raw JSON / technical names? | Legacy shape puts `str(evidence.value)` into strengths and field keys into evidence; breakdown keys not remapped. |
| Why evidence/gaps/risks/score contradict? | Soft components + terra narrative vs eligibility voided by CK overlay failure vs hardcoded risk + null score. |
| Does Ranking use current V2 CV facts / person-aware authority? | Uses ranking evidence/facts snapshots + `person_id` in provenance; **CK live ranking reader is enabled but failing** (`UndefinedFunction`), so person-aware CK path denies/voids score instead of enriching it. Not a clean “V2-only” path. |
| Stale / incomplete / other schema? | Run is fresh, but score publication incomplete; UI still on legacy presentation schema. Recalc jobs exist for other roles (e.g. ACCOUNTING) as pending historically. |
| People or applications? | Ranking pool/items are **applications** (with optional `person_id`). |
| Is Overview card based on completed ranking? | **No.** |

**Layers:** ranking contract (CK overlay fail-closed) + presentation (legacy FE) + frontend routing (manual Rank) + Overview aggregation (signal sum). **Systemic.**

---

## Cross-cutting issues

### People vs applications (systemic)

Overview / Reports / mobile priorities count **applications**. Candidates list displays **people** via `aggregateCandidatesForList`. Labels almost always say “candidates”.

Affected: Overview cards, hero reasons, Top priorities, Candidates footer, Assistant read tools that reuse overview counts.

### Filters & URLs (systemic)

- Overview applies filters in React state only.
- `writeDashboardUrl` persists `page` (+ `candidate`), not `follow_up` / `review_status` / `assessment_status` / `position`.
- Browser Back restores page, not the Overview promise.
- Interview next-action filters (`needs_scheduling`) are ignored by `applyOverviewDestination`.

### Assessment send path (systemic)

| Surface | Cohort rule | Send CTA |
|---|---|---|
| Overview count + Candidates `awaiting` | assigned `pending\|in_progress\|expired` | no inline bulk send |
| Assessments page queue | FE `''\|pending` only | Send button |
| Live WATHEFNI | mostly **expired** | Resend belongs on Attempts, not Overview “Send” |

### EN / AR / RTL

- Overview has locale toggle and AR copy in `recruitingLifecycle.ts`; `dir=rtl` on Overview root.
- Ranking page copy is largely **English-only** (no parallel AR strings for Rank / fit summary / breakdown).
- Shell chrome outside Overview may remain EN depending on page — Overview-local localization only.

### Local vs production code drift

Local `wathefni-orchestrator/prehire_overview.py` still documents assessment pending as `''|pending`. Production counts `pending|in_progress|expired` (assigned attention). Audits/fixes must target production definitions.

---

## Mismatch register

| ID | Mismatch | Layer | Isolated / systemic | Best long-term correction | Pages / modules |
|---|---|---|---|---|---|
| M1 | Cards say “candidates”; counts are applications | Presentation + count contract | Systemic | Publish dual metrics `{applications, people}` from `prehire_overview`; labels must name the unit | Overview, Reports, Assistant reads, mobile priorities |
| M2 | Follow-up **4** opens **2** people | Backend apps + FE person aggregation | Systemic | Same as M1; optional person-first overview counts | Overview → Candidates |
| M3 | Assessment **3** opens **2** people; “Send” copy vs expired assigned | Backend definition + routing + Assessments FE queue | Systemic | Split “needs first send” vs “needs resend/attention”; route Send CTA to Assessments with matching queue | Overview, Candidates, Assessments |
| M4 | Accounting Excel **3** vs Ranking **1** | Aggregation (signal sum) | Systemic | Role card value = distinct apps or people for that role, never sum of overlapping flags; show signal chips separately | Overview role card, Ranking |
| M5 | Overview role CTA does not load ranking | Frontend routing | Systemic | Auto-fetch latest run (or force recalculate) when opening Ranking from Overview | Overview, Ranking |
| M6 | Rank required after recommendation | Frontend routing / incomplete destination | Systemic | Same as M5; destination should be “ranked result”, not “empty ranker” | Overview, Ranking |
| M7 | Score `0/100` while narrative positive | Ranking contract (CK fail-closed) + FE null→0 | Systemic | Fail-open or soft-degrade CK reader errors; never present null advisory as 0; show eligibility/score state explicitly | Ranking BE/FE, CK ranking reader |
| M8 | Raw JSON / technical field names in Ranking UI | Presentation / legacy adapter | Systemic | HR-facing presentation layer: humanize evidence, map component keys, hide raw objects | Ranking page, `to_legacy_rank_candidates_shape` |
| M9 | Evidence / gaps / risks / score contradict | Ranking contract + presentation | Systemic | Single decision object: eligibility, advisory score, narrative, missing evidence must share one state machine | Ranking |
| M10 | Overview role pressure ≠ completed ranking | Product contract | Systemic | Either stop linking role pressure to Ranking, or require/show last run summary on the card | Overview, Ranking |
| M11 | Hamad/Aziz repeated in Top priorities | Work-queue grain vs “people” copy | Systemic | Person-first queue with nested actions/apps, or label “actions” and group by person | Overview work queue |
| M12 | View all is expand-only | Frontend routing | Isolated-ish | Real work-queue page or deep-link to filtered Candidates by action | Overview |
| M13 | Interview CTA drops filters | Frontend routing | Systemic | Honor `destination.filters` on Interviews | Overview, Interviews |
| M14 | URL/Back lose Overview filters | Frontend routing | Systemic | Encode filters in query string; restore on popstate | Dashboard shell, Candidates |
| M15 | Role next steps can show 0-active / non-priority roles | Aggregation / ordering | Systemic | Sort by pressure (same signals as role priority); hide 0-active or move to Jobs | Overview, Jobs positions |
| M16 | Assessments page send queue ≠ Overview assessment count | Frontend `assessmentQueue` vs overview predicate | Systemic | One shared cohort helper for Overview/Candidates/Assessments | Assessments, Overview |
| M17 | Ranking breakdown schema drift | Presentation | Systemic | Map R0–R3 `component_scores` to UI or render dynamic keys | Ranking FE |
| M18 | Local overview module stale vs production | Repo drift | Systemic | Sync/pin production assessment pending definition into repo | `prehire_overview.py` |

---

## Destination matrix (every CTA)

| UI control | Promised records | Opens | Exact match? | Extra steps? |
|---|---|---|---|---|
| Hero primary (follow-up) | failed-delivery candidates | Candidates `follow_up=needed` | Apps yes / people fewer | Open profile / recover delivery |
| Hero primary (ready) | ready-for-decision candidates | Candidates `review_status=ready` | Apps yes | Decide on profile |
| Hero primary (assess) | awaiting assessment | Candidates `assessment_status=awaiting` | Apps yes / people fewer | Find Send/Resend elsewhere |
| Hero primary (role) | role pressure | Ranking + position | Count mismatch | Must press Rank |
| Hero Check ranking | same role | Ranking + position | same | Must press Rank |
| Review ready card | ready apps | Candidates ready filter | Yes (apps) | Profile decision |
| Send assessments card | pending assessment | Candidates awaiting | Yes (apps) | Not Assessments send surface |
| Follow-up card | follow-up apps | Candidates follow-up | Yes (apps) | Profile / outbound |
| Role attention card | role “3” | Ranking | Shows 1 after Rank | Rank + interpret broken score UI |
| Top priority row | that action’s person/app | Candidate profile | Yes for app | Act on profile |
| View all | rest of queue | In-page expand | N/A | No navigation |
| Role next steps row | that job’s candidates | Candidates by position | Position filter yes | May include quiet/0-active jobs |

---

## Consistency across surfaces

| Surface | Unit | Ready | Follow-up | Assessment attention | Ranking |
|---|---|---|---|---|---|
| Overview | apps (labels: people) | 3 | 4 | 3 | role signal sum |
| Candidates filters | apps → person rows | same predicate | same | same awaiting predicate | n/a |
| Assessments page | attempts + divergent FE queue | n/a | n/a | **different** | n/a |
| Ranking | applications in job pool | n/a | n/a | unused in this run | 1 for ACCOUNTING_EXCEL |
| Candidate profile | person + selected app | stage labels | outbound state | assessment attempt | optional stored eval |
| Jobs / Role next steps | positions + stage_counts | bottleneck language | not wired | not wired | not wired |

---

## Recommended long-term correction (no changes in this audit)

1. **One unit vocabulary:** every Overview number declares `entity: application|person|action|job` and UI copy matches.
2. **Person-aware Overview projections** that reuse Candidates identity rules, without changing lifecycle authority.
3. **Role card = distinct actionable apps/people + separate signal chips**; never additive overlap.
4. **Destination completeness:** Overview → Ranking must load/show latest run; Overview → Assessments for send/resend must use identical cohort helper.
5. **Ranking presentation contract:** eligibility, advisory score, narrative, evidence, gaps share one state; FE never invents `0` from null; no raw JSON in HR UI.
6. **Fix CK ranking reader `UndefinedFunction` fail-closed path** so reader failures cannot void otherwise usable CV soft scores without an explicit HR-facing error.
7. **Persist destination filters in the URL** and honor interview filters.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Overview claims match counted entity | **FAIL** |
| Card click opens exact promised records | **FAIL** (people vs apps; role 3→1; assess send surface) |
| Filters understandable & durable | **FAIL** (no URL persistence; interview filters dropped) |
| Duplicates explained / correct grain | **FAIL** for “people” framing (correct for action×app) |
| Destinations actionable without busywork | **FAIL** (Rank click; assess send elsewhere) |
| Cross-page stage/count consistency | **FAIL** (Assessments queue; Ranking presentation) |
| Ranking coherent with Overview recommendation | **FAIL** |
| EN/AR/RTL complete for Overview path | **PARTIAL** (Overview ok; Ranking EN-heavy) |

### Final: **FAIL** for the Overview experience

Audit complete. No code, UI, count, filter, ranking, lifecycle, or data changes were made.
   