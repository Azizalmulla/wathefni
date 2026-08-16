# Candidates URL / filter-state authority — Wave 3 (local)

**Verdict: PASS**  
**Stamp:** `20260801T021633Z`  
**Deploy:** none  
**Wave 4:** not started  
**Filter UI redesign:** none (layout preserved)

## Scope

Durable Candidates URL + filter-state authority only:

- every meaningful flat filter that affects the applications API (plus deep-link context) is written to / restored from the dashboard URL
- clearing Follow-up needed clears `follow_up`, `overview_cohort`, `cohort_key`, and `action`
- saved-view select **replaces** filter state (no merge leftovers)
- stage (`status`) and view pills now survive reload / back / forward
- backend predicates, counts, permissions, tenant isolation, and filter layout unchanged

## Affected filters

| Filter / control | API | Saved views | URL (Wave 3) | Reload / back-forward |
|---|---|---|---|---|
| Search `q` | yes | yes | yes | yes |
| Stage toolbar `status` | yes | yes | **yes (new)** | **yes (was wiped)** |
| View pills `view` | yes (unified) | yes | **yes (new)** | **yes (new)** |
| Job `position` | yes | yes | yes | yes |
| Follow-up `follow_up` | yes | yes | yes | yes |
| Assessment status | yes | yes | yes | yes |
| Interview status | yes | yes | yes | yes |
| Sort | yes | yes | yes (non-default) | yes |
| Source / CV status / recruiter / CV processing / received dates | yes | yes | **yes (new)** | **yes (new)** |
| Review status (Overview deep link) | yes | yes | yes | yes |
| `overview_cohort` / `cohort_key` / `action` | cohort / context | yes if present | yes | yes |
| Classification dims | yes when enabled | yes | **no** (session + saved views; nested) | via saved view only |
| Ghost advanced (activity / grounded / completeness / dept tag) | yes if set | yes | yes if set | yes if set |

## Exact URL contract (`page=candidates`)

Written only when on Candidates. Defaults omitted: `view=all`, `sort=newest`.

| Query key | Maps to |
|---|---|
| `page` | `candidates` |
| `candidate` | open profile `app_key` |
| `q` | search |
| `status` | stage toolbar |
| `view` | view pills |
| `position` | job filter |
| `follow_up` | follow-up predicate |
| `review_status` | ready-for-review deep link |
| `assessment_status` | assessment filter |
| `interview_status` | interview filter |
| `sort` | sort (omit when `newest`) |
| `overview_cohort` | Overview cohort predicate / context |
| `assessment_cohort` | mirrored when assessment-style cohort |
| `cohort_key` | stable cohort id (nav only) |
| `action` | work-queue action context (nav only) |
| `cv_status` | CV status |
| `source_channel` | source |
| `recruiter_owner` | recruiter |
| `cv_processing_state` | CV processing |
| `received_from` / `received_to` | received date range |
| `activity_from` / `activity_to` | activity range (if set) |
| `has_grounded_email` / `has_grounded_phone` | grounded flags (if set) |
| `fact_completeness` / `department_intake_tag` | unified extras (if set) |

### Follow-up clear contract

Removing Follow-up needed (Follow-up select → any, or Clear advanced filters) clears:

1. `follow_up`
2. `overview_cohort`
3. `cohort_key`
4. `action`

Unrelated filters (e.g. `position`, `status`, `q`) are preserved.

### Saved views vs URL

- Save still stores `{ query, status, ...candidateFilters, classification }`.
- Select now **replaces** from `EMPTY_CANDIDATE_FILTERS` via `candidateFiltersFromSavedViewBlob` (no leftover merge).
- After select, continuous URL sync writes the durable flat subset; classification remains in React/saved-view blob only.

## Files

- `apps/wathefni-dashboard/src/lib/candidateFilterAuthority.ts` (new)
- `apps/wathefni-dashboard/src/lib/candidateFilterAuthority.test.ts` (new)
- `apps/wathefni-dashboard/src/lib/dashboardNavigation.ts`
- `apps/wathefni-dashboard/src/lib/dashboardNavigation.test.ts`
- `apps/wathefni-dashboard/src/App.tsx`
- `apps/wathefni-dashboard/src/pages/CandidatesPage.tsx`
- `apps/wathefni-dashboard/src/pages/CandidatesWave3Contract.test.tsx` (new)

## Proofs

| Gate | Result |
|---|---|
| Reload keeps active flat filters (URL round-trip) | **PASS** |
| Back/forward restores via `popstate` + `status`/`view` restore | **PASS** (code + unit) |
| Shared URLs reproduce same durable keys | **PASS** |
| Saved views replace; no leftover follow-up conflict | **PASS** |
| Clearing one filter preserves unrelated | **PASS** |
| Follow-up clear drops quartet | **PASS** |
| EN/AR + RTL (`dir`) | **PASS** |
| Targeted Vitest | **35 passed** |
| Deploy | **not done** |
| Wave 4 | **not started** |

## Tests

```
vitest: candidateFilterAuthority + dashboardNavigation + CandidatesWave3Contract + App + ClassificationFilters
→ 5 files / 35 tests PASS
```

Log: `verify/targeted-tests-final.log`
