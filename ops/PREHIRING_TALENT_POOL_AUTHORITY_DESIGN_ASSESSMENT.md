# Pre-Hiring Talent Pool — Authority and Migration Design Assessment

**Status:** read-only design assessment — **no code, schema, data, or deploy changes**  
**Date:** 2026-07-25 (Kuwait) · **extended** with Role Profile / Hiring Brief  
**Inputs:** `ops/PREHIRING_INTAKE_OCR_AND_TALENT_POOL_AUDIT.md`, frozen Candidates / Jobs / Ranking / Reports / Assistant / lifecycle green pins, live production (`candidates.phone` · `applications.app_key` · `candidate_ranking.py` · `job_ranking_criteria_*`)  
**Production pin context:** document journey green `6018796d…` (orthogonal)  
**Owner constraint:** Do **not** implement Talent Pool Option B yet — design only.

---

## Verdict

### Talent Pool person/application authority

**Prefer Option B** (productized held-intake as General Applications / Talent Pool) over Option A (candidate-without-application) for the first Talent Pool ship — **when** owner authorizes implementation. Option A still reopens frozen application-centric modules.

### Role Profile / Hiring Brief (this extension)

**Recommend a separate `Role Profile` entity** — not a draft/private Job Opening, and not “every ranking must use a draft job.”

Companies that receive large CV volumes but **do not create or publish jobs in Wathefni** need a first-class Hiring Brief that:

- stores title, department, skills, experience, education, languages, location, seniority, criteria/weights, exclusions, notes, versions;
- drives **advisory** Talent Pool ranking only;
- **never** creates an application, advances lifecycle, or contacts a candidate;
- leaves **frozen job-based Ranking** unchanged;
- can later convert to a real open Job with explicit HR confirmation.

**OCR `residence` allowlist** remains an orthogonal micro-fix.

---

## Part I — Talent Pool person/application options (prior)

### Option A — True Talent Pool authority

```text
Person/Candidate may exist with no Application
Application created only after explicit linking to a real job
```

### Option B — Productized held-intake authority

```text
Keep today’s Candidate + held Application (needs_role / import_review)
Present as General Applications / Talent Pool in UX
Keep held records excluded from lifecycle and job Ranking
HR link to open Job = assign + intake_admit → ready_for_review
```

### Side-by-side (person model)

| Dimension | A · Candidate-only | B · Held-intake |
|---|---|---|
| Frozen Candidates lifecycle | **High** — reopen C0–C1 | **Low** — `intake_admit` already exists |
| Ranking (job-based) | Must prove exclusion | Already excluded via predicates |
| Reports / Assistant | New surfaces or drift risk | Invisible to reviewable predicates |
| Email / WhatsApp / bulk | Create-path rewrite | Keep create paths |
| Historical `needs_role` | Dual universe or backfill | **Are** the pool — no backfill |
| Migration / rollback | High | Low |
| GCC unsolicited volume | Cleaner person model later | Scales now; surrogate-phone clutter risk |

### Explicit answers (person model) — summary

1. Schema allows candidate without application; **product create paths do not** — unsafe as Talent Pool authority today.  
2. Candidates / Ranking / Reports / Assistant / Offers / Interviews assume **application** work items.  
3. Candidate-only records **reopen** frozen authority.  
4. Historical `needs_role` coexist with B **without backfill**.  
5. Best risk path: **B when shipping Talent Pool**; defer A.  
6. HR link authority: assign open job + `intake_admit` only.  
7. Duplicates: **no silent merge** — HR-confirmed link suggestions.  
8. Consent/retention/delete: additive on intake events under B.  
9. Job-bound email alias: auto-admit only if open + tenant opt-in; else hold.  
10. Paused/closed/missing job: hold (email/bulk); WhatsApp APPLY hard-rejects.

*(Full prior detail retained in git history of this file’s first revision; substance unchanged.)*

---

## Part II — Role Profile / Hiring Brief

### Problem statement

Some GCC tenants will:

- forward / upload **large CV volumes**;
- keep people in Talent Pool / General Applications;
- **not** create or publish Job Openings in Wathefni for months;
- still need HR and AI Recruiter to **compare** pool members against a hiring need.

Today’s frozen Ranking authority is:

```text
rank_job_applications(company, position_code)
  → load positions row
  → load approved job_ranking_criteria_sets for that position_code
    (or automatic_role_profile fallback)
  → score applications bound to that position_code
```

Live production has `candidate_ranking.py` and `job_ranking_criteria_*` tables. Criteria are **always keyed to `(company_code, position_code)`**. Draft/paused jobs can still be ranked by code (status not gated), but:

- they pollute **Jobs** inventory and Jobs authority;
- intake accidentally publishing/opening is a real foot-gun;
- companies that “don’t use Jobs” still must fake jobs;
- Talent Pool held apps (`needs_role`) are **excluded** from job Ranking pools — so a fake draft job **does not** rank the pool unless you incorrectly bind pool apps to that `position_code` (which risks duplicate applications and lifecycle leakage).

Therefore a **Role Profile** must be first-class and **separate from a public Job Opening**.

### Required Role Profile fields

| Field | Notes |
|---|---|
| Role title | Required |
| Department | Optional |
| Required / preferred skills | Structured lists |
| Experience range | Min/max years or bands |
| Education / certifications | Structured |
| Languages | Structured |
| Location | Text / structured |
| Seniority | Enum / text |
| Ranking criteria + weights | Versioned; hard/soft classification |
| Exclusions | Hard disqualifiers |
| Notes | Free text |
| Version history | Append-only sets + actor + timestamp |

### Required Role Profile authority

| Rule | Contract |
|---|---|
| Rank Talent Pool vs Role Profile | Allowed |
| Ranking kind | **Advisory only** |
| Create Application | **Forbidden** as a side effect of ranking |
| Change candidate/application lifecycle | **Forbidden** |
| Contact candidate | **Forbidden** |
| AI Recruiter grounding | Must name the **selected Role Profile** (id + title + version) **or** explicitly say **no valid ranking context** |
| Later link to real open Job | Explicit HR confirmation only (reuse B’s `intake_admit` path) |
| Frozen job Ranking | **Unchanged** — separate code path / run kind / tables or clearly namespaced |

### Clarification: “without creating an Application”

Under recommended Talent Pool **Option B**, pool members already have **held** applications (`needs_role`). Role Profile ranking may **score those held rows** without:

- creating a **new** application;
- admitting them (`intake_admit`);
- assigning `position_code` of a real Job;
- writing job `ranking_runs` that imply pipeline eligibility.

True “person with zero applications” ranking remains **Option A** and stays deferred.

---

## Part II — Role Profile implementation options

### RP-1 — Reuse job/criteria structures with private non-published role mode

```text
positions row with status=draft|internal + visibility≠public
job_ranking_criteria_sets still keyed by position_code
```

| Pros | Cons |
|---|---|
| Reuses criteria tables / approve flow | Conflates Jobs and Hiring Briefs |
| Less new schema | Foot-gun: publish/open enables intake |
| | Jobs list / Assistant job tools polluted |
| | Frozen Jobs transitions/permissions entangled |
| | Ranking pool still job-application-bound — does not score `needs_role` without unsafe rebinding |
| | Companies “without jobs” still create fake jobs |

**Impact on frozen Jobs/Ranking:** Medium–High (semantic overload of `positions`).

### RP-2 — Separate Role Profile entity (recommended)

```text
role_profiles (company-scoped)
role_profile_versions / criteria_sets / criteria
role_profile_ranking_runs (advisory, separate from ranking_runs)
pool = held intake applications (Option B) or future persons (Option A)
```

| Pros | Cons |
|---|---|
| Clean authority split from Job Opening | New schema + APIs + UI |
| Frozen job Ranking untouched | Must teach AI Recruiter a new context object |
| Natural for no-job / high-volume tenants | Conversion-to-Job must be explicit and tested |
| Criteria versioning owned by profile | |
| GCC scale: many briefs, few openings | |

**Impact on frozen Jobs/Ranking:** **Low** if job Ranking code paths are not reused for side effects (may share pure scoring functions).

### RP-3 — Require every ranking context to use a draft job

```text
No Role Profile; HR must create draft job to rank
```

| Pros | Cons |
|---|---|
| Zero new entity | Worst UX for “we don’t post jobs” |
| | Same foot-guns as RP-1 |
| | Forces Jobs module for Talent Pool value |
| | Still doesn’t score held pool without rebinding |

**Reject** for the stated tenant class.

### Role Profile options scorecard

| Concern | RP-1 private job | RP-2 separate entity | RP-3 always draft job |
|---|---|---|---|
| Frozen Jobs | At risk | Protected | At risk |
| Frozen job Ranking | Entangled | Isolated | Entangled |
| Criteria versioning | Job-local | Profile-local (clear) | Job-local |
| Talent Pool ranking | Awkward / unsafe rebind | Native advisory pool | Awkward |
| AI Recruiter grounding | Ambiguous “job” | Explicit profile id | Ambiguous |
| Reports | Job metrics polluted | Separate advisory reports | Polluted |
| Convert to real Job | “Publish draft” (dangerous if intake opens) | Explicit convert API | Same as RP-1 |
| Duplicate applications | High if rebinding pool apps to draft `position_code` | Low if no rebind until admit | High |
| Migration / rollback | Medium | Additive tables; flag OFF | Medium |
| GCC scalability | Poor for no-job tenants | Good | Poor |

---

## Part II — Detailed assessments

### Impact on frozen Jobs and Ranking

| Surface | Contract |
|---|---|
| `prehire_jobs` create/publish/pause/close | Unchanged |
| Intake accepts only `open` jobs | Unchanged |
| `job_ranking_criteria_*` / `ranking_runs` | Remain **job-only** authority |
| New Role Profile ranking | New run kind, e.g. `role_profile_ranking_runs`, or `ranking_runs.kind='role_profile_advisory'` with hard exclusion from Candidates UI “official rank” |
| Shared math | Optional pure functions for soft scores — **not** shared write path to job current-run |

### Criteria versioning

Recommended model (mirrors job criteria without sharing PK):

```text
role_profile
  └── role_profile_criteria_set (version, status=draft|approved, evidence_policy, actor)
        └── role_profile_criteria (type, label, hard|soft, weight, rule_json, exclusions)
```

- Approving a set increments version; marks prior advisory runs stale.  
- Does **not** call `mark_runs_stale` on **job** ranking runs.  
- Permissions: prefer `prehire.read` to view; new `role_profile.manage` (or reuse `jobs.edit` only if owner accepts coupling — **prefer separate permission** so non-job tenants aren’t forced through Jobs publish).

### Talent Pool ranking (advisory)

```text
Input:
  - company_code
  - role_profile_id + criteria_version (or latest approved)
  - pool = applications WHERE status IN needs_role|import_review
           AND company_code = …
           (Option B)

Output:
  - ordered advisory scores + component breakdown + provenance
  - stored as advisory run (not Candidates “current rank”)

Forbidden side effects:
  - UPDATE applications.status
  - UPDATE applications.position_code
  - intake_admit
  - outbound message / WhatsApp / email
  - writing job ranking_runs.is_current
```

Empty pool → valid run with zero items (still grounded on profile).  
No approved criteria → AI/UI must say **no valid ranking context** (or use explicit “unapproved draft profile” only if HR opts in — default refuse for Assistant).

### AI Recruiter grounding

| Situation | Required assistant behavior |
|---|---|
| HR selected Role Profile P vN | Every rank/compare answer cites **P title + id + criteria version N** |
| No profile selected / none approved | Explicit: **no valid ranking context** — do not invent a job or silent criteria |
| Job Ranking tool invoked | Remains job-scoped; must cite **Job Opening** `position_code`, not a Role Profile |
| Ambiguous “rank tellers in the pool” | Ask which Role Profile; do not auto-pick a draft job |

New tool (design): `rank_talent_pool_against_role_profile` — separate from `rank_candidates`.

### Reports

| Report class | Behavior |
|---|---|
| Pre-hire pipeline / hiring funnel | **Ignore** advisory profile runs |
| New optional “Talent Pool advisory” export | Profile id, version, run id, scores — labeled advisory |
| Job Ranking reports | Unchanged |

### Conversion Role Profile → real Job

Explicit HR action only:

1. Choose Role Profile version V.  
2. `create_job` as **draft** (or draft→open in a second confirm).  
3. Copy criteria set V into `job_ranking_criteria_sets` as version 1 approved **for that new `position_code`** (or require separate jobs.publish approve — owner choice).  
4. Optionally offer “admit selected pool members to this job” → per-person `intake_admit` with confirmations — **never** bulk-silent.  
5. Role Profile remains; job does not delete it.

**Do not** implement conversion as “flip draft job to open” without a Role Profile entity — that is RP-1.

### Duplicate applications

| Anti-pattern | Why forbidden |
|---|---|
| On rank, `UPDATE applications SET position_code=DRAFT_ROLE` | Creates false job binding; may unique-index / lifecycle interact; pollutes job Ranking |
| Auto-create second application for same phone+job on convert | Must use existing same-role uniqueness rules after admit |
| Silent merge of email surrogate and WhatsApp | Still forbidden |

Safe convert: admit **existing** held `app_key` onto open job via `intake_admit`.

### Migration and rollback

| Step | Rollback |
|---|---|
| Additive `role_profiles*` tables | Drop unused tables / flag OFF |
| Advisory ranking APIs | Disable flag; job Ranking unaffected |
| Assistant tool | Remove from catalog |
| No backfill of fake draft jobs required | — |

### Long-term GCC scalability

| Pattern | Fit |
|---|---|
| Banks/telcos with standing briefs + seasonal openings | Role Profiles ≫ Jobs; convert when headcount approved |
| Agencies / high inbound email | Profiles + Talent Pool advisory rank; Jobs only when client opening exists |
| Classic job-post tenants | Keep using frozen job Ranking; Profiles optional |

---

## Combined recommended architecture

```text
Talent Pool (Option B — when approved to implement)
  = held applications (needs_role | import_review | import_archived)
  = no job Ranking, no lifecycle, no auto-contact

Role Profile / Hiring Brief (RP-2)
  = separate entity + versioned criteria
  = advisory Talent Pool ranking only
  = AI must ground on selected profile or refuse

Job Opening (frozen)
  = positions + intake + job Ranking + Candidates lifecycle
  = unchanged

Bridge
  = explicit HR: Profile → create Job (copy criteria)
  = explicit HR: Pool member → intake_admit onto open Job
```

```text
                    ┌─────────────────────┐
                    │   Role Profile      │
                    │   (Hiring Brief)    │
                    └─────────┬───────────┘
                              │ advisory rank only
                              ▼
┌──────────────┐      ┌─────────────────────┐
│ Email/Bulk/  │─────▶│ Talent Pool (held   │
│ WhatsApp CV  │      │ needs_role apps)    │
└──────────────┘      └─────────┬───────────┘
                              │ explicit intake_admit
                              ▼
                    ┌─────────────────────┐
                    │ Open Job Opening    │──▶ frozen job Ranking
                    │ Candidates lifecycle│
                    └─────────────────────┘
```

---

## Compatibility with “rank without Application”

| Interpretation | Supported by recommendation? |
|---|---|
| Do not create a **new** application when ranking | **Yes** |
| Do not admit / bind to a Job when ranking | **Yes** |
| Score held `needs_role` applications against a Profile | **Yes** (Option B pool) |
| Score persons with **zero** application rows | **No** until Option A Person Registry |

Owner should treat “without creating an Application” as **no side-effect application mint/admit**, not as “schema forbids held apps.”

---

## OCR correction (unchanged)

Add canonical `residence` to identity OCR allowlist; keep `residency`; keep `authoritative: false`. Separate micro-remediation.

---

## Frozen-module impact (updated)

| Module | Talent Pool B | Role Profile RP-2 |
|---|---|---|
| Jobs | Untouched | Untouched if no fake draft jobs |
| Job Ranking | Untouched | Untouched (separate advisory authority) |
| Candidates lifecycle | Untouched except admit bridge | Untouched |
| Assistant | Optional copy | **New tool + grounding rules** (additive) |
| Reports | Untouched | Optional advisory export |
| Document journey | OCR allowlist optional | Untouched |

---

## Recommended model (final)

1. **Do not implement Option B yet** (per owner).  
2. When Talent Pool ships: **Option B** held-intake authority.  
3. For no-job / high-volume ranking: **Role Profile separate entity (RP-2)** + advisory pool ranking.  
4. **Reject RP-1 and RP-3** as primary design (draft/private jobs as briefs).  
5. **Defer Option A** person-without-application.  
6. Keep frozen job Ranking and Jobs lifecycle exactly as production-green.

---

## Exact implementation sequence (when owner authorizes)

**Do not start until owner decisions below are answered.**

0. **Freeze this assessment** — no code.  
1. **OCR micro-fix** (optional independent): `residence` allowlist + journey regression.  
2. **Role Profile schema + CRUD + criteria versioning** (flagged OFF) — no ranking yet.  
3. **Advisory Talent Pool rank API** against Role Profile using **held** apps only — prove: no lifecycle write, no outbound, no job `ranking_runs.is_current`.  
4. **AI Recruiter tool** `rank_talent_pool_against_role_profile` with mandatory profile citation / refuse-without-context.  
5. **UI:** Role Profiles + “Rank pool against brief” (still no Option B rename required, but pool = Import Review / held).  
6. **Convert Profile → draft/open Job** (copy criteria) — explicit confirms.  
7. **Talent Pool Option B UX** (rename Import Review, consent/retention, duplicate suggestions, Setup Console intake).  
8. **Link selected pool members → open Job** via existing `intake_admit`.  
9. Re-qualify frozen Jobs + job Ranking + Candidates + Assistant matrices.  
10. Only later: Option A Person Registry if still required.

Rollback at each step: feature flags OFF; job Ranking paths never share writes.

---

## Explicit owner decisions required

### Prior (Talent Pool person model)

1. Approve **Option B** for eventual Talent Pool ship (not now)?  
2. Defer **Option A** Person Registry?  
3. Naming: Talent Pool vs General Applications vs Import Review.  
4–10. Auto-admit, subject codes, consent, retention, duplicate link, OCR allowlist, Setup Console scope — as in prior list.

### New (Role Profile)

11. Approve **RP-2 separate Role Profile entity** (recommended)?  
12. Reject using draft/private jobs as Hiring Briefs (RP-1/RP-3)?  
13. Permission model: new `role_profile.manage` vs reuse `jobs.edit` / `jobs.publish`? (**Recommend new permission.**)  
14. May Assistant use unapproved draft profile criteria, or only approved versions? (**Recommend approved-only.**)  
15. On Profile→Job convert: auto-approve copied job criteria, or require `jobs.publish` again?  
16. May advisory rank include `import_archived`, or only `needs_role`/`import_review`?  
17. Should Role Profile land **before** Talent Pool UX rename, given no-job high-volume tenants? (**Recommend yes — steps 2–5 before 7.**)

---

## Stop

Assessment extended. **Do not implement Talent Pool Option B, Role Profile, or OCR changes from this document alone.**  
Await owner decisions.
