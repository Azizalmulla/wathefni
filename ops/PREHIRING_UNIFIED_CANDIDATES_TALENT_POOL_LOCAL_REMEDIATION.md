# Pre-Hiring Unified Candidates + Talent Pool — Local Remediation

**Date:** 2026-07-25  
**Scope:** Local implementation and qualification only  
**Deployment:** **Not deployed.** Stopped before staging/production.

## 1. Authority decisions

| Decision | Resolution |
| --- | --- |
| Workspace model | One Candidates table for held Talent Pool rows and live applications |
| Held active statuses | `needs_role`, `import_review` only |
| Archived held | `import_archived` and nullable/archived governance → Archived view |
| Restricted | Governance `restriction_state` / legal-hold / deletion-pending excluded from normal views |
| Lifecycle isolation | Ranking, Reports, Interviews, Offers, and lifecycle mutation paths unchanged |
| Held actions | Preview/download CV only; never notify, evaluate/rank, assess, interview, shortlist, reject, hire, or offer |
| Link to Job | UI/API designation present and **disabled**; does not call `intake_admit` or import assignment |
| Fact authority | Extraction snapshots immutable (`application-cv-facts-v1`); HR review is append-only with supersession |
| Privacy | Nullable governance hooks; default message `Privacy and retention policy not configured` |
| Surrogate keys | Never search or display `imp-…` phones/keys |
| Search | Tenant-scoped metadata/CV/facts/education + existing embeddings for similarity only; disclosed match reasons |
| Intake Review on Candidates | Removed; replaced by processing-attention banner → read-only Intake Operations |

## 2. Changed files (this remediation)

### Backend
- `wathefni-orchestrator/unified_candidates.py` — view predicates, governance schema, enrichers, search reasons, fact review, saved views, Intake Operations summary
- `wathefni-orchestrator/app.py` — schema ensure; held action gating in `_application_ui_contract`; unified `GET /dashboard/prehire/applications` (`view` + filters); profile/facts/review; saved-views CRUD; intake-operations (+ attention); held evaluation denial
- `wathefni-orchestrator/test_unified_candidates.py` — authority unit tests
- `wathefni-orchestrator/local-qualify-unified-candidates.py` — residue-clean synthetic matrix

### Dashboard
- `apps/wathefni-dashboard/src/components/candidates/CandidatesTable.tsx`
- `apps/wathefni-dashboard/src/components/candidates/CandidatesTable.test.tsx`
- `apps/wathefni-dashboard/src/components/candidates/CandidateGovernedProfile.tsx`
- `apps/wathefni-dashboard/src/components/candidates/IntakeOperationsPage.tsx`
- `apps/wathefni-dashboard/src/App.tsx` — unified Candidates workspace, banner, Intake Operations page, held → governed profile
- `apps/wathefni-dashboard/src/App.test.tsx` — `view=all` / attention / saved-views mocks
- `apps/wathefni-dashboard/src/lib/api.ts`
- `apps/wathefni-dashboard/src/types.ts`
- `apps/wathefni-dashboard/src/lib/recruitingLifecycle.ts`

### Evidence
- `ops/screenshots/unified-candidates/unified-candidates-table.png`
- `ops/screenshots/unified-candidates/candidate-governed-profile.png`
- `ops/screenshots/unified-candidates/intake-operations.png`
- `ops/screenshots/unified-candidates/INDEX.md`
- `ops/PREHIRING_UNIFIED_CANDIDATES_TALENT_POOL_LOCAL_REMEDIATION.md` (this file)

## 3. Additive schema (idempotent)

- `candidate_record_governance` — recruiter/tag + privacy/retention/restriction/archive/legal-hold/deletion/tombstone hooks
- `candidate_fact_review_events` — append-only confirm/correct/reject/add/supersede
- `candidate_saved_views` — tenant + actor scoped filter JSON

## 4. Read APIs added/extended

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/dashboard/prehire/applications` | Extended with `view=all\|active\|talent_pool\|hired\|archived\|restricted` + filters; legacy callers without `view` keep prior reviewable predicate |
| GET | `/dashboard/prehire/applications/{app_key}/profile` | Governed profile composition |
| GET | `/dashboard/prehire/applications/{app_key}/facts` | Snapshot + effective facts |
| POST | `/dashboard/prehire/applications/{app_key}/facts/review` | Append-only review |
| GET/POST/DELETE | `/dashboard/prehire/candidates/saved-views[/{view_id}]` | Tenant+actor saved views |
| GET | `/dashboard/prehire/intake-operations` | Read-only processing buckets |
| GET | `/dashboard/prehire/intake-operations/attention` | Banner counts |

## 5. Screenshots (local Chromium)

Captured 2026-07-25 with installed headless Chromium from deterministic synthetic fixtures mirroring production components. Temporary capture harness removed after capture; PNGs retained.

1. **`ops/screenshots/unified-candidates/unified-candidates-table.png`**  
   All view; processing-attention banner; six view pills; held row (`Not linked` / `Talent Pool` / `—` / `No outreach`) beside live row; columns Candidate, Job, Entry method, Status, Recruiter owner, CV processing, Assessment, Communication only.

2. **`ops/screenshots/unified-candidates/candidate-governed-profile.png`**  
   Held profile with sender provenance separated from CV contacts, `Skills/Languages not extracted`, privacy default wording, disabled Link to Job, lifecycle-action denial copy.

3. **`ops/screenshots/unified-candidates/intake-operations.png`**  
   Read-only buckets (queued / incomplete / quarantined with release forbidden / ready held); no duplicate candidate list.

## 6. Local test matrix

| Suite | Result | Notes |
| --- | --- | --- |
| `python3 -m unittest test_unified_candidates` | **9/9 PASS** | View predicates, surrogate hide, held action denial, fact precedence, privacy default, search reasons |
| `python3 local-qualify-unified-candidates.py` | **37/37 PASS** | Synthetic tenant records; zero-residue counters; no classification/ranking/job-binding/outbound mutations |
| Dashboard Vitest | **12 files / 54 tests PASS** | Includes Candidates views, held/live rendering, Intake Operations link, App loading with `view=all` |
| Dashboard `npm run build` | **PASS** | `tsc -b && vite build` |
| HR mobile Vitest | **11 files / 44 tests PASS** | |
| HR mobile `npm run typecheck` | **PASS** | No `build` script on this package; typecheck used |

### Residue-clean proof (synthetic matrix)

Teardown counters asserted all zero for:

`companies`, `applications`, `candidates`, `fact_review_events`, `saved_views`, `outbound_delivery_events`, `candidate_rank_evaluations`, `lifecycle_events`

Plus explicit non-mutation checks for classification, ranking, job binding, and outbound.

## 7. Frozen HEAD regression evidence

Branch under test: `authority-cutover` (local working tree).  
Sibling branch `candidates-c3-local` exists but was **not** merged for this qualification.

| Suite | Result | Notes |
| --- | --- | --- |
| Candidates C0/C1 local contract docs + scripts present | **Present** | `ops/CANDIDATES_C0_C1_LOCAL_IMPLEMENTATION.md`, `ops/candidates-c01-*.py` |
| C0/C1 live DB matrices | **Not executed** | Require orchestrator runtime env + DB (`application_environment` binding) |
| `smoke-test-prehire-overview-unit.py` | **PASS** | |
| `smoke-test-canonical-recruiting-lifecycle.py` | **PASS** (unit portion) | DB portion skipped: `psycopg2 not available` / no bound env |
| `smoke-test-offer-lifecycle.py` | **PASS** | Authority + schema contract |
| `smoke-test-prehire-assistant-parity.py` | **PASS** | |
| Bulk CV import / tiered intake smokes | **Scripts present; not DB-executed** | Documented to run with orchestrator venv + database |
| `smoke-test-interview-workflow.py` | **Not DB-executed** | Needs full orchestrator env |
| `smoke-test-summary-counts.py` / `smoke-test-assistant-hr-reads.py` | **Not DB-executed** | Fail closed on missing `application_environment` |

### Qualification limitations (branch-only packs not on HEAD)

The following source packs are **not present on this branch** and are recorded as limitations rather than claimed executions:

- Candidates C2 / C3 packs
- Ranking R0–R3 packs
- Reports V1 pack
- Assistant A0–A3 source packs

They appear associated with `candidates-c3-local` / related workstreams, not this HEAD tree.

## 8. Residual risks

1. **DB-backed frozen matrices not re-proven on this laptop** — unit/contract coverage is green; full C0/C1, bulk/tiered, interview, summary-count DB proofs still need a bound orchestrator environment before staging trust.
2. **Screenshot fixtures are deterministic HTML mirrors** of production component contracts, not a live authenticated dashboard session against a tenant DB.
3. **Working tree is dirty with unrelated changes** outside this remediation (e.g. delivery deletions, other apps). Staging promotion must cherry-pick / isolate only the unified-candidates file set above.
4. **Saved views + governance tables are additive** — first deploy must run schema ensure; rollback must leave tables inert/unused without dropping if rows exist.
5. **Link to Job remains intentionally disabled** — product must not interpret the control as available intake admission.
6. **Search semantic path reuses embeddings only** — operators must not assume held rows enter Ranking evaluation artifacts.

## 9. Guarded staging deployment / rollback sequence

**Do not run until explicitly approved. This local remediation stops here.**

### Deploy (guarded)

1. Isolate a commit containing only the unified-candidates files listed in §2 (exclude unrelated tree dirt).
2. Deploy orchestrator first; confirm `ensure_unified_candidates_schema` creates the three additive tables idempotently.
3. Smoke on staging with a **synthetic throwaway tenant** only (never production Talent Pool data as the first proof):
   - `view=all|active|talent_pool` counts
   - held row action denial (`allowed_actions` ⊆ preview/download)
   - profile privacy default + missing-fact wording
   - fact review append + supersede; snapshot hash unchanged
   - saved view CRUD scoped to actor
   - Intake Operations attention banner ≠ duplicate candidate list
   - search reason disclosure; restricted rows absent from All
4. Deploy dashboard build; visual check against §5 screenshots.
5. Re-run frozen DB matrices on staging (C0/C1, bulk, tiered, lifecycle, offers, interviews, overview, assistant parity) before any production promotion.
6. Explicitly verify zero new: rank evaluations for held rows, outbound deliveries, job bindings, classification artifacts, lifecycle events outside expected CV/intake paths.

### Rollback

1. Revert dashboard to prior Candidates build (removes unified pills/profile/Intake Operations page).
2. Revert orchestrator routes/enrichment; leave additive tables in place (do not DROP if any staging rows were written).
3. Confirm legacy `GET /dashboard/prehire/applications` without `view` restores prior reviewable behaviour.
4. Confirm Ranking / Interviews / Offers / lifecycle mutation paths unchanged by comparing pre-deploy smoke baselines.

## 10. Stop statement

Local implementation, tests, residue-clean synthetic matrix, available frozen HEAD unit/contract suites, Chromium screenshots, and this remediation report are complete.

**No staging or production deployment was performed.**
