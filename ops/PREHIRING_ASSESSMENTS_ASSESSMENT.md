# Pre-Hiring Assessments — End-to-End Assessment

**Assessment date:** 2026-07-24 (Kuwait)  
**Mode:** Read-only code, test, configuration, and production-data inspection  
**Implementation/deployment:** None  
**Frozen authorities left unchanged:** Jobs Phase 1–2; Candidates C0–C3; Ranking R0–R3; Reports V1; Pre-Hiring Assistant A0–A3; Jobs/Ranking UX remediation; Ranking result presentation UX

## Executive verdict

**Verdict: the core attempt, answer, scoring, and immutable-report authority is technically strong, but the end-to-end Assessments product is not yet enterprise-ready under the stated optional-assessment contract.**

The core Assessments runtime should **not** be rewritten:

- attempts are tenant- and application-bound;
- only one open attempt per application is enforced;
- content is snapshotted and pinned to each attempt;
- answers are transactionally serialized and idempotent;
- final scores and reports are immutable and reproducible;
- candidate tokens are random, hashed at rest, expiring, and revocable;
- scoring is deterministic and AI cannot alter it;
- production AI authoring is disabled.

The blockers are at contained product/integration boundaries:

1. **Production Ranking currently consumes assessment evidence without an explicitly approved employer policy.** One current `ranking-soft-v2` item includes a 7.26/15 assessment component from a 48.4% attempt. Its committed score is 41.86; the same committed non-assessment components normalize to 40.71. Production has zero approved `job_ranking_criteria_sets`. This is a live, measurable change in leaderboard meaning without the required employer approval.
2. **The assessment work queue presents optional assessments as pending work for all eligible candidates.** Production reports `assessment_pending=2` while `ready_for_review=3`; code calls these candidates “awaiting assessment,” applies a 72-hour SLA, and says candidates “need an assessment sent.”
3. **Arabic delivery is not a qualified end-to-end path.** Arabic and English beta item banks exist, but the candidate page is hard-coded `lang="en"`, LTR, and English-only. Production also routes dashboard sends through the action registry, whose executor ignores requested battery, locale-derived battery, expiry, and actor provenance.
4. **Ranking does not bind optional evidence to an employer-selected assessment definition/version.** It consumes the latest completed same-position attempt regardless of battery approval or selected version. A retry or different battery can silently change which score is consumed.
5. **Assessment lifecycle changes do not mark assessment-informed Ranking runs stale.** Send, completion, cancellation, and expiry paths never invoke the existing Ranking stale authority, so a displayed supplementary result can remain based on obsolete assessment state.
6. **Module-off does not remove assessment evidence from Ranking or general Reports exports.** Ranking has no assessments-module gate, and the general candidate CSV always joins and exports assessment status.
7. **Module-off is not invisible.** Assessment wording remains in normal Jobs, Settings, candidate drawer, Ranking, public-link, Assistant-tool, and mobile paths.
8. **One public mutation remains executable module-off.** The candidate cancel endpoint validates the token and cancels the attempt without checking the tenant module.

These findings do **not** justify reopening the frozen CV Ranking formula. The smallest safe boundary is:

> Keep CV Ranking independent. Default assessment consumption to unused unless a versioned employer policy explicitly selects the assessment definition/version; show assessment results separately until that policy exists.

### Readiness by authority

| Authority | Verdict | Enterprise readiness |
|---|---|---|
| Attempt/content/scoring core | Strong and internally coherent | Ready for controlled English fixed-bank use |
| Delivery and candidate access | Secure but operationally incomplete | Material remediation required |
| Arabic candidate experience | Not end-to-end qualified | Blocked for bilingual enterprise claim |
| Assessment definition authoring | Safe by being disabled in production | No action recommended until authoring is an approved product |
| Assessment-to-Ranking integration | Violates explicit-approval contract | Confirmed blocker |
| Reports parity | Export exists; summary metrics incomplete | Material defect |
| Assistant parity | Confirmed send only; no status/explain/resend/cancel | Partial capability, not full parity |
| Module-off entitlement boundary | Primary nav/API gating exists, but cross-surface leaks remain | Confirmed blocker |

## Scope and evidence standard

Evidence used:

- current orchestrator and dashboard source under `/tmp/wathefni-c3-local`;
- current production service configuration and aggregate, non-PII database queries on 2026-07-24;
- existing unit/smoke/qualification tests;
- read-only test executions during this assessment.

No conclusion below treats a theoretically desirable enterprise feature as a defect. Missing features are defects only where they violate the stated Wathefni contract or produce a demonstrated failure.

## Production truth snapshot

Read-only production inspection found:

| Evidence | Production observation |
|---|---|
| Assessment module | Enabled for 1 company |
| Batteries | 3: one active global English/default bank; two WATHEFNI EN/AR beta banks |
| Items / content versions | 72 items; 3 frozen content versions |
| Attempts | 4 total: 1 completed, 3 expired |
| Responses / scores / reports | 22 responses; 1 score; 1 report |
| Immutability | 0 mutable scores; 0 mutable reports |
| Version integrity | 0 attempts missing a version; 0 score/report version mismatches |
| Open-attempt integrity | 0 duplicate-open application groups |
| Tenant/application integrity | 0 orphan attempts |
| Delivery history | all 4 attempts have `delivery_status=pending`; 0 invitation rows; 0 token rows |
| Audit | 7 assessment events |
| Authoring/AI | `WATHEFNI_ASSESSMENT_AUTHORING=false`; 0 drafts; 0 AI runs; all model registry versions disabled |
| Ranking policies | 0 approved job criteria/evidence-policy rows |
| Current Ranking | 7 current `ranking-soft-v2` items; 0 required-assessment missing codes; 0 legacy approval-missing codes; 1 item includes assessment points |
| Optional queue | `assessment_pending=2`, `ready_for_review=3` |

The zero production invitation/token rows and `pending` delivery status are consistent with migrated historical attempts: the cleanup migration pins versions and defaults missing delivery state to `pending` but cannot reconstruct old delivery events (`ops/migrate-assessments-cleanup1.py:87-155`).

## Current architecture

### Authority separation

1. **Assessment product authority**
   - definitions: `assessment_batteries`, `assessment_items`, frozen `assessment_content_versions`;
   - runtime: `assessment_attempts`, `assessment_responses`, `assessment_scores`, `assessment_reports`;
   - access/delivery: `assessment_tokens`, `assessment_invitations`;
   - audit: `assessment_events`;
   - authoring: drafts, revisions, reviews, blueprints, translations, AI registry/prompts/runs/events.

2. **CV Ranking authority**
   - job-scoped `ranking_runs` and `ranking_run_items`;
   - CV facts, CV evidence materializations, semantic evidence, job criteria;
   - assessment is only an input selected by `candidate_ranking.py`, not the assessment score authority.

3. **Current optional integration**
   - Ranking’s job-pool query selects the latest assessment attempt for each application (`candidate_ranking.py:1062-1072`);
   - `soft_component_scores` accepts a completed, scored attempt linked only by matching `position_code` (`candidate_ranking.py:1404-1439`);
   - available components are renormalized to 100 (`candidate_ranking.py:1480-1511`);
   - the frozen assessment score is not rewritten, but Ranking ordering can change.

### Runtime flow

```text
HR/dashboard/Assistant send
  → application tenant binding
  → resolve battery
  → reuse one open attempt or create a version-pinned attempt
  → issue hashed bearer token
  → send email + WhatsApp
  → candidate browser state
  → one transactional answer per item
  → synchronous deterministic score/report
  → immutable score/report + completed event
  → non-authoritative application.raw_json assessment projection
  → optional Ranking reader may consume latest same-position result
```

### Legacy and parallel paths

| Path | Status | Assessment |
|---|---|---|
| Seeded live bank in `app.py` | Live; upserts on schema startup | Legacy monolith definition source, but frozen snapshots protect attempts |
| `assessment_lifecycle.py` / `assessment_service.py` | Canonical cleanup authority | Current runtime safety primitives |
| Dashboard direct send | Exists | Bypassed in production because registry flag is `all` |
| Action-registry send | Live in production | Parallel path; currently loses battery/expiry/requested-by parameters |
| HMAC assessment helpers | Still present | Legacy compatibility; current persisted token path uses random hashed tokens |
| Application `raw_json.assessment` | Projection only | Can drift; must not be treated as score authority |
| Product-2 AI authoring | Staging-only, no publish route | Not a live definition authority; compiled competency shape is not compatible with the live scorer |
| WhatsApp assessment answers | Explicitly disabled | WhatsApp returns a browser link; browser is answer authority |

## Table and schema inventory

### Live definition/runtime tables

| Table | Purpose and key controls | Evidence |
|---|---|---|
| `assessment_batteries` | Battery identity (`battery_key` PK), tenant/global scope, active/retired state, content version, scoring/report metadata | `app.py:2152-2162`; `assessment_lifecycle.py:52-56` |
| `assessment_items` | Ordered questions, choices, answer key, deterministic scoring metadata | `app.py:2163-2176` |
| `assessment_norm_groups` | Section norm cutoffs, sample/source/version metadata | `app.py:2177-2188` |
| `assessment_content_versions` | Immutable-intent battery/items/scoring/norm snapshot with SHA-256 and version uniqueness | `assessment_lifecycle.py:63-78` |
| `assessment_attempts` | Tenant/application/candidate/job/battery/version/status/progress/expiry/delivery/review | `app.py:2190-2207`; `assessment_lifecycle.py:80-130` |
| `assessment_responses` | One response per attempt/item, answer/scoring snapshots, score, final flag | `app.py:2209-2221`; `assessment_lifecycle.py:132-137` |
| `assessment_scores` | One score per attempt, percent/band/sections/norm/version, immutable flag | `app.py:2223-2234`; `assessment_lifecycle.py:139-140` |
| `assessment_reports` | One frozen report JSON per attempt/version | `app.py:2236-2242`; `assessment_lifecycle.py:141-142` |
| `assessment_events` | Append-only-intent attempt lifecycle audit | `assessment_lifecycle.py:144-157` |
| `assessment_tokens` | Hashed bearer token, purpose, expiry, use, revocation | `assessment_lifecycle.py:159-172` |
| `assessment_invitations` | Per-channel send record and provider/outbound reference | `assessment_lifecycle.py:174-195` |

### Authoring/AI tables

| Table | Purpose | Production state |
|---|---|---|
| `assessment_item_drafts` | Human/AI draft lifecycle | 0 rows; authoring off |
| `assessment_item_reviews` | Deterministic, model, and human review evidence | Inactive in production |
| `assessment_blueprint_versions` | Versioned approved authoring blueprints | Seeded schema; not live publishing |
| `assessment_ai_model_registry_versions` | Provider/model/environment/version approvals | 5 rows, all disabled |
| `assessment_prompt_versions` | Versioned prompts/schema/rubric hashes | 5 active prompt records |
| `assessment_ai_runs` | Input/output hashes, model IDs, tokens, cost, status, errors | 0 production runs |
| `assessment_item_draft_revisions` | Append-only draft content/scoring revisions | Staging authoring only |
| `assessment_translation_pairs` | EN/AR pair and equivalence-review authority | Staging authoring only |
| `assessment_eval_runs` | Qualification evidence | Staging/offline only |
| `assessment_authoring_events` | Authoring audit | Staging authoring only |

### Schema observations

- The partial unique index allows one open attempt per `(company_code, app_key)` (`assessment_lifecycle.py:125-127`).
- Definitions and historical evidence are content-addressed, but the database does not itself forbid `UPDATE`/`DELETE` of content-version, score, or report rows. Application code never updates completed evidence, and production has zero mutable scores/reports. **Classification: unknown pending evidence** until deployed DB grants confirm the application/ops roles cannot bypass the immutable write path; a trigger is not recommended without that evidence.
- `assessment_items.battery_key` and `assessment_attempts.app_key` are not declared foreign keys in the base schema. Runtime tenant/application validation compensates for current writes.
- `assessment_items` has no `company_code`, but this is **not** evidence of cross-tenant mixing: `assessment_batteries.battery_key` and item IDs are globally unique primary keys (`app.py:2152-2175`). Tenant-specific banks must use distinct keys. **Classification: no action recommended** absent evidence that same-key tenant overrides are an approved requirement.
- Startup seeding updates the live bank in place and then freezes it using the unchanged battery `content_version` (`app.py:2806`, `app.py:2835-2839`, `app.py:28338-28426`). If seeded content changes, its new digest can collide with the existing unique `(company_code,battery_key,content_version)` release. This fails closed rather than rewriting history, but can fail application startup.
- No job-to-battery policy table exists.
- No retry-parent or selected-authoritative-attempt relation exists.
- No retention policy columns or cleanup schedule were found.

## API inventory

### Candidate/public

| Method/path | Authority | Notes |
|---|---|---|
| `GET /assessment/{attempt_id}` | Static candidate page | Token validated only by state/answer calls |
| `POST /assessment/{attempt_id}/state` | Token + attempt state | Starts pending attempt immediately |
| `POST /assessment/{attempt_id}/answer` | Transactional answer/scoring | Stale progress and invalid choices fail closed |
| `POST /assessment/{attempt_id}/cancel` | Candidate cancel | Not exposed in browser UI |

Evidence: `app.py:37725-37820`.

### Dashboard

| Method/path | Permission | Behavior |
|---|---|---|
| `GET /dashboard/prehire/assessments` | module + `prehire.read` | Tenant-scoped attempts/list metrics |
| `GET /dashboard/prehire/assessments/config` | module + `prehire.read` | Batteries, item-bank counts, norms, guardrails |
| `GET /dashboard/prehire/assessments/batteries/{key}/items` | read; keys require `assessment.manage` | Definition inspection |
| `POST /dashboard/prehire/applications/{app_key}/assessment` | `assessment.manage` | Create/reuse and deliver |
| `POST /dashboard/prehire/assessments/{id}/resend` | `assessment.manage` | Revoke old tokens, issue/send new link |
| `POST /dashboard/prehire/assessments/{id}/cancel` | `assessment.manage` | Terminal cancel + revoke |
| `POST /dashboard/prehire/assessments/{id}/review` | `assessment.manage` | Mark completed report reviewed |
| `GET /dashboard/prehire/assessments/{id}` | `prehire.read` | Exact attempt/report/responses |
| `GET /dashboard/prehire/assessments/{id}/report` | `prehire.read` | HTML report |
| `POST /dashboard/prehire/assessments/norms/recalculate` | `assessment.manage` | Preview or persist empirical norms |

Evidence: `app.py:47992-48594`, `app.py:52228-52294`.

### Authoring

All authoring routes require `assessment.manage` and a non-production flag. Product-2 routes include status, model activation, eval recording, blueprint versioning, generation, manual drafts, secondary review, bilingual adaptation/review, human rewrite, evidence, and run status. No publish route exists (`assessment_ai_routes.py:1-5`, `assessment_ai_routes.py:77-482`).

## Capability matrix

Legend: **R** read; **M** mutation; **Confirm** is the current UI/Assistant confirmation contract.

| Capability | Backend authority | Permission | Confirm | Lifecycle effect | Audit | Production status / finding |
|---|---|---|---|---|---|---|
| Create assessment definition | Product-2 drafts/blueprints | `assessment.manage` | N/A | None | Authoring events/reviews | Disabled in production; no publish. **No action recommended** until authoring is approved |
| Edit/version definition | Draft revisions + content snapshots | `assessment.manage` | Human transitions | None | Revision/review events | Staging-only; live fixed banks |
| Retire definition | Draft/blueprint lifecycle and battery `retired_at` | `assessment.manage` in authoring | Human | Prevent selection | Review/events | Partially modeled; no live dashboard control |
| Assign definition to job | None | — | — | — | — | No explicit job-definition authority |
| Select battery on send | Request supports `battery_key`/locale | `assessment.manage` | Dashboard send confirm | Creates/reuses attempt | Attempt/event | Production registry path ignores selection; **material defect** |
| Approve for Ranking | Ranking evidence policy | `jobs.publish`/policy authority | Explicit UI confirm | Stales Ranking run | Criteria-set approval | Policy exists, but default optional is consumed without explicit approval; **blocker** |
| Send one candidate | `send_assessment` | `assessment.manage` | Yes in dashboard/Assistant | No application stage change; creates pending attempt | Attempt/event/invitation/action result | Live |
| Bulk send | Assistant batch/workflow only | batch + `assessment.manage` | Preflight + confirm | Per-app attempts | Batch/action audit | No dashboard bulk UX; **optional enhancement**, not a defect |
| Candidate complete | Browser answer route | bearer token | Candidate choice | Attempt completed only | Answer/completion events | Live |
| Resume | Server current index + reusable token | bearer token | No | None | token `used_at`/events | Live and sufficient |
| Expiry | Attempt/token timestamps, lazy expiry | bearer/HR action | No | Attempt expired | expiry/revocation events | Enforced on access; no sweep, so dashboard can be stale |
| Retry/reset | New attempt after terminal completion/cancel/expiry | `assessment.manage` | Send confirm | New independent attempt | New events | No retry relation or authoritative-attempt policy |
| Scoring | Frozen version + deterministic code | candidate completion | No | Score/report only | immutable score/report + event | Live and strong |
| Manual scoring | None | — | — | — | — | Not required for supported choice-only types |
| Manual review | review endpoint | `assessment.manage` | Yes | review facet only | reviewed event | Live |
| View result | exact report APIs/page | `prehire.read` | No | None | No dedicated view event | Live |
| Export | Reports V1 `assessments` CSV | `report.export` + module | No | None | Reports export authority | Live; report metrics incomplete |
| Assistant send | `send_assessment` ActionSpec | `assessment.manage` | Yes + minted outbound confirmation | Same attempt authority | action result + assessment events | Live; actor not propagated |
| Assistant config/status | Legacy `check_assessment_config`; generic `get_candidate_status` exposes assessment status | module/read permission | No | None | generic action audit | Live but not dedicated score/status authority |
| Assistant explain/resend/cancel | No dedicated tools | — | — | — | — | Absent; classify as **optional enhancement** unless parity is approved |
| HR mobile | Timeline label only | existing candidate read | No | None | None | No assessment management/results surface |
| Candidate mobile web | Responsive browser page | bearer token | No | Same runtime | Same audit | English path usable |
| Arabic candidate flow | Arabic item bank exists | bearer token | No | Same runtime | Same audit | Page chrome/RTL and production selection path not qualified |

## Definition and version authority

### Unique identity

- Mutable/live definition identity: `battery_key`.
- Frozen definition identity: `assessment_version_id`.
- Human-readable version: battery `version` plus integer `content_version`.
- Integrity identity: `content_sha256`.
- Question identity: `item_id`; order: `item_order`.

### Historical immutability

`freeze_current_content_version` snapshots battery metadata, approved items, scoring rules, norm groups, report logic, and a content digest (`assessment_service.py:22-149`). New attempts pin `assessment_version_id` (`app.py:29488-29544`). Responses store answer/scoring snapshots (`app.py:29872-29900`). Completion inserts score/report once and rejects conflicting immutable evidence (`app.py:29663-29717`).

**Classification: already sufficient.** Current live-bank edits do not reinterpret old attempts.

### Live-bank release behavior

The seed path upserts live batteries/items on startup (`app.py:28338-28425`), but attempt creation chooses the latest existing content version and freezes only when none exists (`app.py:29488-29506`). There is no production publish route.

The startup path itself also calls `freeze_current_content_version` after every seed (`app.py:2835-2839`). A code change to seeded content produces a new digest without automatically advancing `content_version`, so the freeze can fail on the existing version uniqueness constraint.

**Classification: material defect in fixed-bank release hygiene, not historical-score integrity.** Current frozen attempts remain safe. The smallest remediation is a release check that requires an explicit version increment whenever the seed digest changes. Live authoring remains future scope.

### Job linkage and multiple assessments

- An attempt copies application `position_code`/title.
- There is no authoritative job-to-battery assignment.
- One job may therefore receive different batteries through sends.
- One application can have multiple terminal attempts, but only one open attempt.
- Ranking checks only attempt/job position equality, not selected battery/version.

**Finding: confirmed blocker at the optional Ranking boundary.** Exact evidence: `candidate_ranking.py:1410-1424`. Consequence: any completed same-position battery can change Ranking, even if the employer never selected that definition/version.

### Employer approval meanings

Current approval concepts are distinct:

- `approved_for_use_beta` in battery JSON: selectable for HR send;
- authoring `approved`: draft lifecycle only; no publish;
- Ranking evidence policy: required/optional/unused;
- HR report `reviewed`: acknowledgment only.

The active global production battery has no explicit approval actor/time/status metadata. One content version has no `created_by_user_id`.

**Classification: material defect.** It does not corrupt scores, but production cannot prove who approved the default definition for assignment or Ranking use.

## Assignment and delivery analysis

### Scope and duplicate prevention

- Scope is a specific tenant application (`company_code`, `app_key`), not a global person.
- Creation verifies the application and phone under the same tenant (`app.py:29452-29467`).
- A partial unique index and `ON CONFLICT` make concurrent open-attempt creation idempotent (`app.py:29468-29576`).
- Resending reuses the open attempt, revokes prior tokens, and issues a new token (`app.py:30254-30273`).

**Classification: already sufficient.**

### Secure links and tenant isolation

- tokens are 32-byte URL-safe random values;
- only SHA-256 hashes are stored;
- validation joins token, attempt, and company;
- cancelled/completed/expired/revoked links fail closed;
- another tenant cannot answer with the token under a different company binding.

Evidence: `assessment_lifecycle.py:551-614`; `assessment_service.py:191-248`; cleanup staging checks `smoke-test-assessments-cleanup1.py:262-307`.

**Classification: already sufficient.**

### Delivery channels and confirmation

Each send creates email and WhatsApp invitation rows and passes one link to the canonical communication router (`app.py:30274-30326`). Channel status becomes `sent` when the router attempt returns `ok`; no later delivery callback updates `assessment_invitations` (`assessment_service.py:324-360`; repository search found no other caller).

**Classification: material defect.**

- Failure/risk: “sent” means accepted by the local/provider send path, not delivered to the candidate.
- Affected: HR tracking and resend decisions.
- Severity: medium.
- Enterprise blocker: no by itself.
- Smallest remediation: label states “send accepted/failed” or reconcile provider delivery events into invitations.
- Leave unchanged: HR may believe a candidate received a link that never arrived.

### Partial-write window

Token/invitation/event creation commits before external delivery (`app.py:30240-30300`); delivery status is written in a later transaction (`app.py:30334-30383`).

**Classification: material defect.**

- Failure/risk: a process crash can leave an active token and “invited” event without a sent message or final channel state.
- Affected: send/resend operations.
- Severity: medium.
- Enterprise blocker: no; manual resend recovers.
- Smallest remediation: recover pending invitations through the existing outbound ledger or mark pre-send events explicitly as queued.
- Leave unchanged: stale pending invitations and ambiguous audit.

### Closed/rejected/hired applications

The queue excludes most terminal stages, but `allowed_actions` appends `send_assessment` for any CV-bearing application with permission (`app.py:41259-41271`), and the send endpoint has no terminal-state guard (`app.py:52228-52261`).

**Classification: material defect.**

- Risk: HR/Assistant can send a new assessment after rejection or hire.
- Affected: terminal candidates and recruiters.
- Severity: medium.
- Enterprise blocker: no.
- Smallest remediation: fail closed for terminal application states unless an explicit, audited override is approved.
- Leave unchanged: confusing or inappropriate candidate contact.

### Multiple applications for one phone

Browser links remain application-specific. The WhatsApp reminder path instead selects the latest open attempt by `(phone, company)` and does not clarify among multiple applications (`app.py:29132-29154`, `app.py:30118-30220`).

**Classification: material defect.**

- Risk: a candidate with two open application assessments can receive the wrong continuation link when messaging WhatsApp.
- Smallest remediation: require application clarification or list both role-labelled links.
- Leave unchanged: wrong-role assessment continuation.

### Lifecycle and Ranking side effects

Sending writes an attempt and an `applications.raw_json.assessment` projection. It does not change canonical application stage; completion creates no offer, employee, hire, or screening rewrite (`smoke-test-assessments-cleanup1.py:375-381`).

**Classification: already sufficient.**

## Candidate flow analysis

### Current flow

1. Open bearer link.
2. Page immediately POSTs state.
3. Pending attempt becomes `in_progress`.
4. One question and choices are shown.
5. Choice is saved transactionally.
6. Server advances to the next item.
7. Final answer synchronously commits immutable score/report.
8. Candidate sees submission confirmation.

### What is sufficient

- Responsive width and mobile viewport.
- Native button controls and keyboard activation.
- Answer keys/scoring are not exposed.
- Every answer is saved before progress advances.
- Reload resumes at server progress.
- stale tabs and double submits fail safely.
- no time limit is intentionally disclosed in dashboard setup (`App.tsx:5567-5569`).
- expiry and invalid links return candidate-safe messages.

### Candidate-flow findings

#### Immediate start without instructions/consent

The page calls state on load (`app.py:36997-37090`), and state changes `pending` to `in_progress` (`app.py:29331-29358`). Unlike the video-interview flow, there is no instructions/consent model for assessments.

**Classification: material defect.**

- Concrete failure: link scanners or accidental opens can mark a candidate in progress before they intentionally begin.
- Affected: candidate status tracking and HR follow-up.
- Severity: medium.
- Enterprise blocker: no for English fixed-bank use.
- Smallest remediation: read-only intro state; start only on an explicit “Begin” action, with a short privacy notice.
- Leave unchanged: false in-progress attempts and missing consent provenance.

#### Arabic/RTL

The page is fixed to `<html lang="en">`, English labels/errors/submission copy, LTR choice layout, and no dynamic `dir` (`app.py:36952-37090`). Arabic items can therefore appear inside English/LTR chrome.

**Classification: confirmed blocker for bilingual enterprise readiness.**

- Affected: Arabic candidates and mixed-content banks.
- Severity: high.
- Smallest remediation: return attempt locale in state, set `lang`/`dir`, localize fixed chrome, and qualify Arabic mobile fixtures.
- Leave unchanged: Arabic beta cannot be represented as an enterprise-ready candidate experience.

#### Save failure recovery

On answer failure, the candidate sees only an error block; the question/choices and explicit retry button are not restored (`app.py:37063-37082`).

**Classification: minor defect.**

- Smallest remediation: restore the same question or add “Try again.”
- Leave unchanged: candidate must reload manually.

#### Refresh after completion

Completion revokes active tokens and token validation rejects completed attempts, so refreshing the final page produces a generic unavailable/completed error rather than the durable submitted confirmation (`assessment_service.py:235-247`; `app.py:29734-29740`).

**Classification: minor defect.**

#### Accessibility

Buttons and saving status are accessible basics, but progress has no ARIA value, focus is not moved after question changes, and locale/direction are wrong for Arabic.

**Classification: minor defect for English; included in the Arabic blocker for Arabic.**

## Question and scoring authority

### Supported live types

| Type | Answer schema | Scoring | Partial credit | Negative marking | Manual/AI grading |
|---|---|---|---|---|---|
| `answer_key` / single choice | selected option key | correct = 1, otherwise 0 | No | No | None |
| `competency_keyed` / situational choice | selected option key | configured `choice_scores`, typically 1–5 | Yes, by choice | No | None |

The authoring contract names `single_choice` and `competency_keyed` (`assessment_ai_contracts.py:27-43`).

### Validation and missing answers

- selected key must exist in frozen choices;
- current item ID and optional `progress_version` must match;
- each attempt/item is unique;
- a different second answer conflicts;
- all frozen items must have responses before completion;
- invalid/missing choices return 422/409 and do not advance.

Evidence: `app.py:29763-29949`, `app.py:29640-29650`.

### Formula

For frozen items \(i\):

```text
raw_score = Σ response.score_numeric
max_score = Σ item.max_score
percent = round(raw_score / max_score × 100, 1)
```

Bands:

```text
80–100  strong
60–79.9 qualified
40–59.9 needs_review
<40      low
```

Section percentages use the same raw/max formula. Ability percentile/T-score/sten are either based on an empirical company norm group with sample size at least 200 or a clearly labelled synthetic fallback (`app.py:28567-28637`). Job-match report logic is deterministic:

```text
ability_fit = weighted average by role profile
competency_fit = weighted average by role profile
job_match = 0.55 × ability_fit + 0.45 × competency_fit
```

Evidence: `app.py:28867-28970`.

### Reproducibility proof

- Attempt content, answer keys, scoring, norms, and report logic are frozen.
- Responses retain scoring/answer snapshots.
- Score/report inserts are one-per-attempt and immutable-conflict checked.
- `smoke-test-assessments.py:69-108` generates the same report twice and asserts exact equality.
- Read-only production tests passed: deterministic assessment smoke, four evidence-policy tests, and 92 Product-2 authority checks.

**Classification: already sufficient.**

### Pass/fail wording

There is no canonical pass boolean. The fixed `qualified` threshold is described as “passed the v1 threshold” (`app.py:28747-28754`).

**Classification: operational/content issue.**

- Risk: HR may interpret a descriptive band as an employer-approved pass/fail decision.
- Smallest remediation: say “qualified band” or require an explicit employer threshold before using “passed.”
- Enterprise blocker: no, provided no automated lifecycle decision uses it.

## AI model and tool inventory

### Production state

- Authoring flag: false.
- AI runs: zero.
- All registry versions: disabled.
- Allowed environments: development/test/staging only.
- No AI scoring, free-text grading, fraud/proctoring, or candidate recommendation path exists.

### Configured roles

| Role | Provider/model | Output | Can publish/score? |
|---|---|---|---|
| `assessment.author_primary` | OpenAI `gpt-5.4` | Generated item package | No |
| `assessment.review_secondary` | OpenAI `gpt-5.4-mini` | Structured item review | No |
| `assessment.adapt_bilingual` | OpenAI `gpt-5.4` | EN/AR adaptation | No |
| `assessment.review_bilingual` | OpenAI `gpt-5.4-mini` | Equivalence review | No |
| `assessment.eval_judge` | OpenAI `gpt-5.4-mini` | Offline eval result | No |

### Controls

- model registry and prompt versions are immutable-intent rows with hashes;
- strict JSON schemas forbid extra fields;
- candidate context is rejected from authoring inputs;
- model output fields for publish/candidate score/decision are rejected;
- deterministic scoring is compiled server-side;
- secondary/human review is required;
- bilingual key/order/scoring invariants fail closed;
- worker refuses production and requires a dedicated limited DB role;
- no Product-2 publish endpoint exists.

Evidence: `assessment_ai_contracts.py:1-6`; `assessment_lifecycle.py:269-502`; `smoke-test-assessment-product2.py:98-313`.

**Classification: already sufficient; freeze production AI authoring.**

Prompt injection exposure is low because candidate text is excluded and no tools are exposed to the authoring model. Item text is model input during secondary review, so hostile draft content could influence review prose, but deterministic checks and mandatory human review prevent it from becoming scoring/publish authority.

### Authoring-to-live compatibility

Product-2 compiles competency scoring as `choice_points` (`assessment_ai_service.py:894-926`), while the live scorer reads `choice_scores` (`app.py:28700-28708`) and the competency report also requires `competencies` weights (`app.py:28891-28900`). Product-2 emits neither live field. Its answer-key compiler may also emit non-unit `correct`/`incorrect` points, while the live answer-key scorer always awards 1/0.

**Classification: operational/content issue, latent while production authoring and publishing remain disabled.**

- Failure/risk: a future publish bridge that copies compiled scoring directly would score competency items as zero and omit competency profiles.
- Affected: future Product-2 publishers and candidates only; no current production attempt.
- Severity: high if publishing is enabled, none today.
- Enterprise blocker: no for the current fixed-bank runtime; yes before any Product-2 publish activation.
- Smallest remediation: add an explicit publish mapper/contract test that emits `choice_scores`, required competency weights, and a single authoritative answer-key point formula.
- Leave unchanged while authoring remains disabled: no production consequence.

## Exact Assessments-to-Ranking relationship

### Live contract

The live contract is:

> CV-first Ranking with an optional assessment component that is automatically consumed when a latest completed same-position attempt exists.

It is not CV-only and not a separately labelled post-assessment mode.

Default policy (`candidate_ranking.py:120-131`):

```text
CV required
screening optional
assessment optional
semantic optional
interview unused
```

Configured soft maxima remain 30 skills + 25 experience + 15 education/certification + 15 assessment + 15 semantic (`candidate_ranking.py:162-169`). Missing optional components are removed from the denominator, so absence does not reduce the score (`candidate_ranking.py:1480-1511`).

### Proof Ranking works before assessment

| State | Current behavior | Proof |
|---|---|---|
| No assessment | Candidate stays in pool; assessment component omitted; remaining components normalize | `test_candidate_ranking.py:1018-1051` |
| Never sent | Same as missing | same code path |
| Pending | optional missing code; component omitted | `candidate_ranking.py:1431-1433` |
| In progress | optional missing code; component omitted | same |
| Expired/cancelled/failed | optional missing code; component omitted | same |
| Unrelated job | `assessment_unrelated_to_job`; component omitted | `candidate_ranking.py:1428-1430` |
| Unapproved under current default | No definition-level approval check exists; completed same-position attempt is consumed | blocker, not independence failure |

Read-only production evidence:

- 7 current Ranking items;
- 0 current `required_assessment_missing`;
- 0 current `assessment_not_employer_approved_for_ranking`;
- current missing/expired assessments remain optional;
- one current item uses assessment evidence.

Therefore the CV leaderboard does operate before assessment and does not zero missing candidates. That part of the contract is **already sufficient**.

### Live contract violation

Production has no approved criteria/evidence-policy rows, yet a current item consumes:

- attempt `e4350bf4-d104-4500-90db-6a0de4205325`;
- frozen version `304b73fa-413a-44ce-a20b-89602ef7dd97`;
- battery `wathefni_ability_v1`;
- immutable score 48.4%;
- normalized assessment component 7.26/15;
- committed Ranking score 41.86 versus 40.71 from the same non-assessment components alone.

`assessment_contribution_approved` is derived as true whenever assessment mode is not `unused`, including the unapproved default policy (`candidate_ranking.py:2491-2495`). The scoring function’s `assessment_contribution_approved` argument is not used to gate the component (`candidate_ranking.py:1328-1439`).

**Classification: confirmed blocker.**

- Failure: optional assessment changes Ranking without explicit employer approval.
- Affected: ranked candidates, recruiters, hiring managers, audit reviewers.
- Severity: high.
- Enterprise blocker: yes.
- Smallest contained remediation: at the integration boundary, treat assessment as `unused` unless an approved job policy exists and selects the exact battery/version; do not alter CV scoring.
- Leave unchanged: leaderboard ordering and score meaning can change silently after an assessment.

### Provenance gaps

Ranking persists attempt ID and evidence policy, but not the consumed assessment version ID, content hash, norm version, battery approval actor/time, or selected policy definition version (`candidate_ranking.py:2618-2645`).

**Classification: confirmed blocker for assessment-influenced Ranking.**

### Retry/latest-attempt behavior

Ranking selects the latest attempt regardless of battery, then checks status/position (`candidate_ranking.py:1062-1072`). A newer pending/expired retry can hide an older completed result; a newer completed retry can replace it.

**Classification: material defect; becomes a blocker whenever assessment affects Ranking.**

### Stale invalidation

Approving a Ranking criteria/evidence policy marks existing runs stale, but assessment send, completion, cancellation, and expiry paths do not call `mark_runs_stale`. Repository searches in the assessment lifecycle/service paths found no Ranking stale transition; the existing stale triggers are criteria-policy and CV-evidence changes.

**Classification: confirmed blocker for assessment-informed Ranking.**

- Failure: a previously calculated Ranking can remain current-looking after the selected assessment state or score changes.
- Affected: recruiters and candidates in any job with supplementary assessment policy.
- Severity: high.
- Enterprise blocker: yes while assessment can affect ordering.
- Smallest contained remediation: invoke the existing Ranking stale authority after a policy-selected attempt completes, is cancelled, expires, or is superseded; recalculate only through the frozen Ranking recalculate path.
- Leave unchanged: displayed ordering can be inconsistent with canonical assessment evidence.

### Stale/legacy presentation

The codebase still contains `assessment_not_employer_approved_for_ranking` and “required assessment” presentation copy (`ranking_result_presentation.py:151-175`, `ranking_result_presentation.py:226-266`). Production shows the legacy code only on non-current `ranking-soft-v1` items; current v2 items have zero occurrences.

**Classification: no action recommended for historical records; material defect if surfaced as current.**

The current dashboard legitimately supports employer policy mode `required`, but the stated product contract says Assessments are optional. Existing copy such as “Assessment needed,” “Ranking paused: required assessments are missing,” and policy help “Missing this evidence pauses Ranking” remains available (`App.tsx:5694-5705`, `App.tsx:6094`; `RankingEvidencePolicyPanel.tsx:16-48`).

**Classification: operational/content issue pending owner decision.** Do not delete historical/advanced policy support solely because it exists; ensure the Wathefni default and current owner-approved contract never select `required`.

## Optional integration options

These are constrained policy choices, not automatic feature recommendations:

1. **Exclude assessment from Ranking (recommended immediate safety state).**
   - CV leaderboard remains unchanged.
   - Assessment result appears separately in candidate/report views.
   - Requires no new formula.

2. **Explicit supplementary signal.**
   - Existing normalization may be used only after employer approval of job, battery, content version, norm version, and policy version.
   - CV-only and assessment-informed values must be separately labelled.

3. **Separate post-assessment Ranking mode.**
   - Only if the owner later approves a distinct mode.
   - Must not overwrite or silently replace the original CV run.

No evidence supports making the current fixed 15-point component the default contract.

## Reports V1 parity

Reports V1 exports one row per assessment attempt with status, score, band, completion, and update timestamps (`reports_v1.py:956-976`). It does not imply every ranked candidate requires an assessment.

However the Reports summary hard-codes:

- `assessment_rows: 0`;
- `assessment_status: []`.

Evidence: `reports_v1.py:508-555`.

**Classification: material defect.**

- Failure: summary/export metadata does not reflect real attempts.
- Affected: HR comparing dashboard and exported counts.
- Severity: medium.
- Enterprise blocker: no for core Assessment scoring; yes for claiming complete Reports parity.
- Smallest remediation: compute attempt count and status breakdown from the same filtered query; distinguish attempts from distinct applications.
- Leave unchanged: count mismatch and misleading empty assessment breakdown.

Reports does not currently distinguish:

- distinct assessed applications;
- abandoned versus expired/cancelled;
- approved-for-Ranking evidence;
- ranked before versus after assessment.

**Classification: optional enhancement**, except approval/ranked-before-after fields become required if assessment-influenced Ranking remains enabled.

## Assistant parity

### Existing send action

`send_assessment`:

- entity: application/candidate `app_key`;
- module: assessments;
- permission: `assessment.manage`;
- preview: candidate, role, channels, secure-link placeholder;
- confirmation: required and sensitive;
- minted outbound confirmation token: covered by Assistant A2 tests;
- backend result: uses canonical `send_assessment`;
- batch/workflow: supported.

Evidence: `action_registry.py:1237-1326`, `action_registry.py:4791-4803`, `tool_call_orchestrator.py:188`.

**Classification: already sufficient for a basic confirmed send.**

The legacy/direct `check_assessment_config` read action exists (`app.py:32672-32706`), and generic candidate status may expose `assessment_status`. Neither is a dedicated attempt-list or score-explanation authority.

### Send provenance/parameter defect

The executor calls `legacy.send_assessment(app, account_id, note=...)` without actor, battery, locale-derived battery, or expiry (`action_registry.py:1067-1091`). Production has `WATHEFNI_PREHIRE_VIA_REGISTRY=all`, so dashboard sends also take this path even though the route constructs those fields (`app.py:52238-52260`).

**Classification: material defect.**

- Failure: explicit battery/locale/expiry requests are silently ignored and assessment events lose requesting actor.
- Affected: dashboard API clients, bilingual sends, audit.
- Severity: high for Arabic selection; medium otherwise.
- Enterprise blocker: contributes to Arabic blocker and approval provenance blocker.
- Smallest remediation: pass these existing parameters through the registry execution context; no new authority.
- Leave unchanged: wrong/default bank may be sent and audit cannot attribute the request.

### Missing tools

No dedicated Assistant tools were found for assessment status, score explanation, resend, cancel/revoke, or listing attempts.

**Classification: optional enhancement.** The Assistant must not invent these capabilities. Until implemented, it should navigate users to Assessments or state that the action is unavailable.

The Assistant should treat “no assessment” as an optional state, not candidate failure. Existing tool descriptions do not prove a score-invention path.

## Module-off invisibility and module-on optionality

### Verdict

**Module-off is partially implemented but does not satisfy the stated invisibility or backend fail-closed contract.**

The dedicated Assessments navigation, page data calls, dashboard assessment routes, candidate summary fields, primary queue items, candidate filters, and assessment export card are gated. However Ranking, general candidate exports, Assistant tool visibility, several normal HR copy surfaces, the public HTML shell, and public cancellation bypass or outlive that boundary.

The module-on optionality contract also fails because an unassigned eligible candidate is counted as assessment-pending, receives a 72-hour assessment SLA, and appears in assessment work queues. This is B2 above.

### Module-off surface matrix

| Surface | Current behavior when disabled | Evidence | Classification |
|---|---|---|---|
| Assessments navigation/page | Nav item is module-filtered; page requests are skipped | `App.tsx:288`, `App.tsx:405-410`, `App.tsx:662-667`, `App.test.tsx:109-137` | Already sufficient |
| Dashboard assessment APIs/direct authenticated URLs | `assessments_dashboard_context` requires module and returns canonical 403 `module_disabled` | `app.py:6298-6380`, `app.py:39072-39073`, `app.py:47992-48007` | Already sufficient |
| Overview assessment work item | Next action and queue item are omitted when `assessments_enabled=False` | `prehire_overview.py:425-441`, `prehire_overview.py:622-658` | Already sufficient |
| Overview raw count/query | `assessment_pending` is always calculated and joins `assessment_attempts`; the flag is explicitly ignored; summary returns the count and assessment definition module-off | `prehire_overview.py:127-167`, `prehire_overview.py:805-826`; `app.py:46017-46030` | Confirmed blocker for pending-count/API invisibility |
| Candidate list/filter/column | Assessment filter, sort, column, and detail card are module-gated | `App.tsx:3374-3401`, `App.tsx:3479`, `App.tsx:3936-3955` | Already sufficient |
| Candidate drawer general copy | Hiring-tab introduction always says “Assessment…” | `App.tsx:3921-3927` | Confirmed blocker under zero-wording contract |
| Quiet Overview copy | Empty-state text can say “review, follow-up, or assessment” without a module argument | `lib/recruitingLifecycle.ts:263` and Arabic equivalent | Confirmed blocker |
| Candidate timeline | Dashboard/mobile timeline label maps assessment event types without a module gate | `CandidateCollaborationPanel.tsx:53`; `wathefni-hr-mobile/src/features/recruiting/CandidateReviewView.tsx:49-60` | Material defect; historical event leak is unqualified |
| Jobs Ranking policy | Panel always includes assessment source/default wording and routes are gated only by Jobs permissions | `components/RankingEvidencePolicyPanel.tsx:13-48`; `App.tsx:4413-4434`; `app.py:49421-49450` | Confirmed blocker |
| Ranking calculation | Always joins latest assessment and defaults assessment mode to optional; no `company_has_module` gate | `candidate_ranking.py:122-131`, `candidate_ranking.py:1021-1072`, `candidate_ranking.py:1404-1439` | Confirmed blocker |
| Ranking wording | “Assessment needed,” required-assessment blockers, and “short assessment” next step are not module-aware | `App.tsx:5694-5705`, `App.tsx:6093-6094`, `ranking_result_presentation.py:1255-1259` | Confirmed blocker |
| Reports assessment export | Dedicated `type=assessments` export requires the assessments module | `app.py:49581-49595` | Already sufficient |
| Reports general candidate export | Always emits an `assessment` column and joins historical attempts under only the pre-hiring report permission | `reports_v1.py:886-914`; report route `app.py:49581-49608` | Confirmed blocker and data leak |
| Reports summary | Invokes canonical counts with `assessments_enabled=True`; that count query always joins assessment attempts | `reports_v1.py:396-404`; `prehire_overview.py:140-157` | Material defect even though current summary does not display the count |
| Assistant UI chips | Dashboard suggestions omit assessment when module is off | `App.tsx:390-402` | Already sufficient |
| Assistant tool execution | `send_assessment` execution fails `module_disabled` | `action_registry.py:4791-4803`; `tool_call_orchestrator.py:567-574`, `tool_call_orchestrator.py:715-737` | Already sufficient |
| Assistant tool visibility | Assessments is not `toolcall_gated`; core assessment tools remain offered to the model | `module_catalog.py:55-64`, `module_catalog.py:228-234`; `tool_call_orchestrator.py:796-837` | Confirmed blocker |
| Settings permissions | Normal Workspace Access renders `assessment.manage` as “Send assessments…” even when the module is off | `App.tsx:413-425`, `App.tsx:6751-6764`; role defaults `app.py:6125-6128` | Confirmed blocker |
| HR mobile candidate summary/home | Assessment detail/item is omitted, but aggregate `total` and `action_counts` still include `assessment_pending` module-off | `operator_mobile_data.py:1496-1502`, `operator_mobile_data.py:2364-2402` | Material defect |
| HR mobile capabilities | Tenant-facing capability payload still exposes an `assessments` key with `reason=module_disabled` | `operator_mobile.py:735-767` | Material defect under invisibility contract |
| Employee mobile | No assessment routes or labels found | repository-wide surface audit | Already sufficient |
| Public state/answer | State checks tenant module before exposing attempt; answer enters through state | `app.py:29321-29328`, `app.py:37730-37737` | Already sufficient |
| Public GET shell | Always returns assessment-branded HTML before the state API rejects access | `app.py:36952-37021`, `app.py:37725-37727` | Confirmed blocker for direct-URL zero-wording |
| Public cancel | Validates token and cancels without a module check | `app.py:37796-37820` | Confirmed fail-closed blocker |
| WhatsApp candidate turn | Returns without continuing the assessment when module is off | `app.py:30128-30133` | Backend safe; candidate-visible disabled wording conflicts with strict invisibility |
| Historical data | Module administration flips `enabled`; no assessment rows are deleted | `app.py:40850-40860` | Already sufficient by source; runtime preservation test absent |
| Cross-tenant access | Attempt/report/token reads bind tenant or token/attempt company | `assessment_service.py:191-248`, `app.py:29271-29280`, `app.py:45610` | Already sufficient |

### Backend behavior

#### Proven fail-closed

- authenticated dashboard reads, sends, resends, reviews, and cancellations;
- public state and answer;
- Assistant action execution and batch execution;
- dedicated Reports assessment export;
- WhatsApp continuation;
- tenant-scoped exact attempt/report reads.

#### Confirmed fail-open or data-consuming paths

1. Public candidate cancellation remains executable with a historical valid token.
2. Ranking reads and may consume historical assessment evidence.
3. Ranking evidence-policy APIs expose assessment configuration under Jobs permissions.
4. General candidate export queries and exports historical assessment status.
5. Assistant exposes the send tool to model selection even though execution later fails.
6. Overview/Reports count authority still queries assessment rows module-off.

#### Disable/enable side effects

Disabling the module changes the registry flag only. It does not delete attempts, responses, scores, reports, tokens, or events and does not recalculate Ranking. Data preservation and no automatic CV-score rewrite are therefore **already sufficient by source**.

However, because Ranking is not module-aware and disable does not mark assessment-informed runs stale, a disabled tenant can retain or recalculate an assessment-influenced result. **Classification: confirmed blocker.** The smallest contained remediation is to make the Ranking integration resolve assessment mode to `unused` module-off and mark only assessment-informed runs stale on disable; never auto-recalculate.

### Module-on optionality

| Contract | Current result | Evidence |
|---|---|---|
| Enabling does not automatically create attempts | Pass | attempts are created only by send/create paths |
| Unassigned candidate has no warning/task/SLA | **Fail** | empty status is pending; 72-hour SLA and queue at `prehire_overview.py:19-38`, `prehire_overview.py:55-67`, `prehire_overview.py:425-441`, `prehire_overview.py:622-658` |
| CV Ranking works without assessment | Pass | optional missing component renormalizes; `test_candidate_ranking.py:1018-1051` |
| Enabling does not change existing CV results | Pass by source | module enable has no recalculate path |
| Missing assessment is not weakness | Partial/fail in presentation | assessment task and “Assessment needed” wording remain |
| Dedicated queue contains assigned attempts only | Exact attempt list passes; “needs send” queue fails | assessment payload reads attempts; frontend secondary queue selects eligible unsent candidates |
| Reports assessment rows are assigned attempts only | Dedicated export passes; general candidate export includes all candidates with nullable status | `reports_v1.py:886-914`, `reports_v1.py:956-976` |

### Two-tenant qualification status

**The requested Tenant A/Tenant B qualification does not exist and cannot pass the current code.**

Existing synthetic assessment suites use two tenants with Assessments enabled for both. They prove tenant isolation, not ON/OFF behavior:

- `smoke-test-assessments-cleanup1.py`: `ASSESSC1A` and `ASSESSC1B`, both module-on;
- `smoke-test-assessments-pagination.py`: `ASSESSPAGEA` and `ASSESSPAGEB`, both module-on.

Current read-only executions:

| Check | Result | What it proves |
|---|---|---|
| `npm test -- --run src/App.test.tsx` | 6/6 passed | Narrow disabled-module nav/Overview/API-call suppression |
| `python3 smoke-test-entitlement-hardening.py` | Passed | Static entitlement/source contracts |
| `python3 smoke-test-toolcall-orchestrator.py` | Passed | Assistant send/batch execution fails module-off |

No existing snapshots or API suite proves zero assessment occurrences across Jobs, Settings, drawer, Ranking, Reports, Assistant, and mobile. The known code paths above mean such a scan would currently fail.

#### Required synthetic qualification matrix

| Assertion | Tenant A — enabled | Tenant B — disabled | Current status |
|---|---|---|---|
| Dedicated module | Visible | Absent | Narrow UI proof only |
| Optional send | Available with permission | Tool absent and execution blocked | Execution passes; tool visibility fails |
| Unassigned candidate | No task/warning/SLA | No wording/count | Fails for A; hidden UI but raw count persists for B |
| Ranking | CV works independently; supplementary only by approved policy | Assessment forced unused; no component/missing code | Missing CV works; both policy gates fail |
| Assessment queue | Assigned attempts only | No surface/query | A fails eligible-unsent queue; B UI hides |
| Reports | Assigned attempts only | No metric/column/query/export wording | Dedicated export gated; general candidate export fails |
| Public URL | Assigned attempt can start | Canonical module-disabled response without branded shell | B shell/cancel fail |
| Historical rows | Preserved | Preserved but hidden | Source-preserved; runtime assertion absent |
| Mobile | Assigned details only | No key/label/reason | Summary passes; capability/timeline proof fails |
| Cross-tenant | No cross-read | No cross-read | Existing both-on isolation proof passes |

Qualification must use:

1. DOM snapshots for Overview, Jobs, Candidates, drawer, Ranking, Reports, Assistant, Settings, and HR mobile with a case-insensitive zero-occurrence assertion for assessment labels in both English and Arabic.
2. HTTP assertions for every dashboard assessment route, public state/answer/cancel, Reports exports, Ranking payload, and action registry.
3. Before/after row counts proving disable preserves attempts/responses/scores/reports/events.
4. Before/after Ranking snapshots proving no automatic recalculate and no assessment component after the existing stale/recalculate authority runs module-off.

Until those assertions pass, module-off must be classified **not qualified**.

## Permissions, tenant safety, and privacy

### Current controls

- all dashboard assessment routes require authenticated tenant context plus the assessments module;
- mutations require `assessment.manage`;
- report export requires `report.export`;
- attempts and exact reports are filtered by `company_code`;
- public access requires the bearer token;
- authoring queries are tenant-scoped;
- candidate context is forbidden from AI authoring;
- default report exports deny protected/sensitive columns.

**Classification: already sufficient for tenant isolation.**

### Result visibility

Any user with assessments module access and `prehire.read` can list attempts and open exact reports; there is no distinct `assessment.results.read` permission or job/manager scope (`app.py:39043-39073`, `app.py:47992-48007`, `app.py:48483-48493`).

**Classification: unknown pending evidence.**

- This is not a defect unless the approved access model requires psychometric-result separation or hiring-manager job scope.
- Required owner evidence: which roles may view item-level answers, score reports, and exports.
- If separation is required, the smallest remediation is a dedicated read permission enforced on report/list routes.

### Retention

No assessment-specific retention or deletion schedule was found.

**Classification: unknown pending evidence.** A legal/tenant retention requirement is needed before recommending schema or cleanup work.

## Reliability and idempotency matrix

| Failure/race | Current control | Residual risk | Classification |
|---|---|---|---|
| Concurrent send/create | partial unique open-attempt index + conflict retry | Reuses one open attempt | Already sufficient |
| Duplicate same answer | unique attempt/item + same-content replay | Returns idempotent | Already sufficient |
| Duplicate different answer | conflict | Fails closed | Already sufficient |
| Concurrent answer tabs | row lock + progress version + conditional index update | One advances; other replays/conflicts | Already sufficient |
| Double final submit | row lock + one score/report + immutable digest check | Safe | Already sufficient |
| Missing answer | completion requires all frozen items | Cannot score incomplete attempt | Already sufficient |
| Stale definition | attempt pinned to snapshot | Safe | Already sufficient |
| Score/report conflict | immutable insert and digest check | Fails closed | Already sufficient |
| Expired link | lazy attempt expiry + token expiry | Dashboard can show stale pending until touched | Material defect |
| Resend | revokes all active tokens, new token | Safe | Already sufficient |
| Delivery provider failure | per-channel failed state | No delivered/reconciled state | Material defect |
| Crash between invitation and send | first transaction already committed | Pending active token/invitation | Material defect |
| Crash after score before projection | core transaction committed; projection is separate | Candidate drawer projection can be stale | Material defect |
| Scoring failure | answer/completion transaction rolls back | Candidate can retry | Already sufficient |
| AI worker failure | staging-only queued run with status/error/retry fields | No candidate runtime impact | Already sufficient |
| Multiple terminal retries | allowed, no parent/selection policy | Latest attempt can change integration | Material defect/blocker when ranked |
| Assessment completes/cancels/expires after Ranking | no assessment-path stale transition | Existing run remains current-looking | Confirmed blocker when assessment-informed |
| Cross-tenant token use | token/attempt/company join | Fails closed | Already sufficient |
| Cleanup/retention | none defined | Unbounded retained evidence | Unknown pending policy |

### Projection drift

Score/report completion commits before `applications.raw_json.assessment` is updated (`app.py:29944-29992`). A post-commit projection failure leaves canonical evidence correct but the candidate summary stale.

**Classification: material defect.**

- Smallest remediation: derive candidate assessment summaries from canonical attempt tables or add an idempotent projection repair.
- Enterprise blocker: no if canonical report/list is used; yes if downstream consumers trust only the projection.

## Classified findings

### Confirmed blockers

#### B1 — Unapproved assessment changes current Ranking

- **Evidence:** `candidate_ranking.py:1404-1511`, `candidate_ranking.py:2491-2495`; production current item detailed above; zero approved criteria sets.
- **Failure/risk:** leaderboard score/order changes without explicit employer approval.
- **Affected:** all candidates in assessment-influenced job runs.
- **Severity:** high.
- **Enterprise blocker:** yes.
- **Smallest remediation:** assessment unused by default unless an approved job policy selects exact definition/version; preserve CV Ranking.
- **Leave unchanged:** silent score-meaning drift and unfair comparison.

#### B2 — Optional assessments are presented as mandatory pending work

- **Evidence:** `prehire_overview.py:19-38`, `prehire_overview.py:55-67`, `prehire_overview.py:425-440`; `App.tsx:5405-5469`; production `assessment_pending=2`.
- **Failure/risk:** users are told candidates need/await assessments even when Ranking and review should proceed independently.
- **Affected:** recruiters, managers, all ready/shortlisted candidates.
- **Severity:** high.
- **Enterprise blocker:** yes under the stated product contract.
- **Smallest remediation:** show only policy-selected/actually assigned assessments as tasks; otherwise label the module as optional.
- **Leave unchanged:** operational pressure to test every candidate and false incompleteness.

#### B3 — Ranking evidence is not bound to selected definition/version

- **Evidence:** latest-attempt query `candidate_ranking.py:1062-1072`; same-position-only gate `candidate_ranking.py:1410-1424`; provenance `candidate_ranking.py:2618-2645`.
- **Failure/risk:** unrelated battery/retry can become Ranking evidence.
- **Affected:** candidates with multiple batteries or retries.
- **Severity:** high.
- **Enterprise blocker:** yes while assessment affects Ranking.
- **Smallest remediation:** integration policy must name battery/content version/norm version and selected attempt rule.
- **Leave unchanged:** non-reproducible policy meaning despite reproducible individual scores.

#### B4 — Arabic candidate delivery is not qualified

- **Evidence:** hard-coded English/LTR candidate page `app.py:36952-37090`; Assessments dashboard is not passed locale/RTL at `App.tsx:2426-2468`; live registry flag; executor parameter loss `action_registry.py:1067-1091`.
- **Failure/risk:** wrong bank/default language and unusable RTL candidate/employer chrome.
- **Affected:** Arabic candidates and Arabic-mode HR users.
- **Severity:** high.
- **Enterprise blocker:** yes for bilingual enterprise claim; no for controlled English-only pilot.
- **Smallest remediation:** parameter passthrough plus localized dynamic `lang`/`dir` page.
- **Leave unchanged:** Arabic beta remains content-only, not a safe product flow.

#### B5 — Assessment lifecycle does not stale assessment-informed Ranking

- **Evidence:** criteria approval stales runs in `candidate_ranking.py:805-861`; no `mark_runs_stale` call exists in assessment send/complete/cancel/expire paths.
- **Failure/risk:** displayed Ranking can retain obsolete assessment evidence.
- **Affected:** candidates, recruiters, and managers using supplementary assessment Ranking.
- **Severity:** high.
- **Enterprise blocker:** yes while assessment affects Ranking.
- **Smallest remediation:** call the existing stale authority only for the affected job/policy and leave recalculation to the approved Ranking path.
- **Leave unchanged:** canonical assessment results and displayed ordering can diverge.

#### B6 — Module-off Ranking and Reports still consume assessment data

- **Evidence:** Ranking always joins attempts and defaults assessment to optional (`candidate_ranking.py:122-131`, `candidate_ranking.py:1021-1072`, `candidate_ranking.py:1404-1439`); general candidate export always joins and emits assessment status (`reports_v1.py:886-914`).
- **Failure/risk:** a disabled tenant can receive assessment-influenced Ranking and assessment data in a normal pre-hiring CSV.
- **Affected:** recruiters/managers in disabled tenants and candidates with historical attempts.
- **Severity:** high.
- **Enterprise blocker:** yes.
- **Smallest remediation:** force the integration mode to `unused` module-off; omit the candidate-export column/join; mark assessment-informed runs stale without auto-recalculation.
- **Leave unchanged:** disabled-module data remains visible and can change leaderboard meaning.

#### B7 — Module-off wording, counts, and tool visibility remain in normal HR surfaces

- **Evidence:** ungated drawer copy (`App.tsx:3921-3927`), Jobs policy (`App.tsx:4413-4434`; `RankingEvidencePolicyPanel.tsx:13-48`), Settings capability (`App.tsx:413-425`, `App.tsx:6751-6764`), Ranking copy (`ranking_result_presentation.py:1255-1259`), summary count/definition (`prehire_overview.py:127-167`, `prehire_overview.py:805-826`), mobile totals (`operator_mobile_data.py:2364-2402`), and Assistant visibility (`module_catalog.py:55-64`; `tool_call_orchestrator.py:796-837`).
- **Failure/risk:** non-admin users are told about a product the tenant does not own; the model can suggest an action that later fails.
- **Affected:** recruiters, managers, candidates opening old links, and HR-mobile users.
- **Severity:** high under the explicit invisibility contract.
- **Enterprise blocker:** yes.
- **Smallest remediation:** use the existing module state to omit these copy/tool/source entries; preserve module setup wording only for authorized administrators.
- **Leave unchanged:** module-off does not behave as though Assessments is absent.

#### B8 — Public module-off boundary is not fully fail-closed

- **Evidence:** public GET always returns assessment-branded HTML (`app.py:36952-37021`, `app.py:37725-37727`); public cancel validates token and mutates without the state/module check (`app.py:37796-37820`).
- **Failure/risk:** stale direct links expose product wording and can cancel historical attempts after module disable.
- **Affected:** candidates and tenant audit/lifecycle records.
- **Severity:** high.
- **Enterprise blocker:** yes.
- **Smallest remediation:** resolve tenant/module before returning the public shell and reuse the canonical module check in cancel.
- **Leave unchanged:** module-off direct URLs remain branded and one mutation remains available.

### Material defects

#### M1 — Registry send loses actor, battery, locale, and expiry

- **Evidence:** production `WATHEFNI_PREHIRE_VIA_REGISTRY=all`; route creates the fields at `app.py:52238-52260`; executor passes only app, account, and note at `action_registry.py:1067-1091`.
- **Failure/risk:** requested bank/locale/expiry is silently replaced by defaults and events lose requesting actor.
- **Affected:** dashboard/Assistant sends, Arabic candidates, auditors.
- **Severity:** high.
- **Enterprise blocker:** contributes directly to B3/B4.
- **Smallest remediation:** pass existing fields through the registry executor.
- **Leave unchanged:** wrong/default bank can be delivered and assignment approval cannot be attributed.

#### M2 — Link open starts the attempt

- **Evidence:** candidate page calls state on load at `app.py:36997-37090`; state changes `pending` to `in_progress` at `app.py:29331-29358`.
- **Failure/risk:** previews, link scanners, or accidental opens create false starts without instructions/privacy acknowledgment.
- **Affected:** candidates and HR pending/in-progress tracking.
- **Severity:** medium.
- **Enterprise blocker:** no for controlled English use.
- **Smallest remediation:** explicit “Begin” transition after an instructions/privacy screen.
- **Leave unchanged:** inaccurate in-progress state and no consent provenance.

#### M3 — “Sent” is not confirmed delivery

- **Evidence:** local router success writes invitation status `sent` at `app.py:30334-30383`; only `create_invitation` and `update_invitation_delivery` call sites exist; there is no later provider-delivery reconciliation.
- **Failure/risk:** HR interprets accepted/enqueued communication as candidate delivery.
- **Affected:** HR resend and follow-up workflows.
- **Severity:** medium.
- **Enterprise blocker:** no.
- **Smallest remediation:** label state “send accepted” or reconcile provider events into invitations.
- **Leave unchanged:** false confidence that a candidate received the link.

#### M4 — Invitation creation and external delivery are split

- **Evidence:** token/invitation/event transaction commits before outbound delivery at `app.py:30240-30300`; final status is committed later at `app.py:30334-30383`.
- **Failure/risk:** process interruption leaves an active token and invited/pending records with no communication.
- **Affected:** send/resend operations.
- **Severity:** medium.
- **Enterprise blocker:** no; manual resend recovers.
- **Smallest remediation:** recover queued invitations through the existing outbound ledger or distinguish queued from sent events.
- **Leave unchanged:** ambiguous audit and candidates who were never notified.

#### M5 — Terminal applications can receive assessments

- **Evidence:** action calculation appends `send_assessment` for any CV-bearing application at `app.py:41259-41271`; send route has no hired/rejected/withdrawn/closed guard at `app.py:52228-52261`.
- **Failure/risk:** new assessment contact after the hiring decision.
- **Affected:** terminal candidates and recruiters.
- **Severity:** medium.
- **Enterprise blocker:** no.
- **Smallest remediation:** deny terminal states unless an explicit audited override is part of the approved workflow.
- **Leave unchanged:** inappropriate contact and inconsistent lifecycle expectations.

#### M6 — WhatsApp chooses one of multiple application assessments

- **Evidence:** `active_assessment_attempt_for_phone` selects the latest open `(phone, company)` attempt at `app.py:29132-29154`; WhatsApp turn handling sends that one link at `app.py:30118-30220`.
- **Failure/risk:** a candidate with two applications can continue the wrong role’s assessment.
- **Affected:** multi-application candidates.
- **Severity:** medium.
- **Enterprise blocker:** no.
- **Smallest remediation:** require clarification or list role-labelled links.
- **Leave unchanged:** wrong-role continuation and candidate confusion.

#### M7 — Expiry is lazy and dashboard state can be stale

- **Evidence:** expiry changes state only when `expire_attempt_if_due` is invoked (`assessment_service.py:251-287`); dashboard list delegates directly to its payload query (`app.py:47992-48001`) and no background expiry worker was found.
- **Failure/risk:** an attempt can remain displayed/count as pending after `expires_at` until candidate or HR interaction.
- **Affected:** assessment queues, SLA counts, follow-up.
- **Severity:** medium.
- **Enterprise blocker:** no.
- **Smallest remediation:** reconcile due attempts on canonical reads or run an idempotent scheduled sweep.
- **Leave unchanged:** status/count mismatches.

#### M8 — Retry attempts lack lineage and authoritative selection

- **Evidence:** one-open index allows new attempts after terminal status (`assessment_lifecycle.py:125-127`); no `retry_of_attempt_id` exists; Ranking selects latest attempt at `candidate_ranking.py:1062-1072`.
- **Failure/risk:** pending retry hides an older completion or a newer completion silently replaces it.
- **Affected:** retry candidates and assessment-informed Ranking.
- **Severity:** high when used by Ranking.
- **Enterprise blocker:** yes if retries can influence Ranking.
- **Smallest remediation:** record retry lineage and define policy-selected authoritative attempt.
- **Leave unchanged:** assessment-informed result meaning can change without a policy event.

#### M9 — Application assessment projection can drift

- **Evidence:** core answer/score/report commits at `app.py:29944-29947`; `applications.raw_json.assessment` updates afterward at `app.py:29964-29992`.
- **Failure/risk:** post-commit failure leaves canonical report correct but candidate summary stale.
- **Affected:** candidate drawer and any projection-only consumer.
- **Severity:** medium.
- **Enterprise blocker:** only if downstream authority relies on the projection.
- **Smallest remediation:** derive summaries from canonical attempt tables or add idempotent repair.
- **Leave unchanged:** conflicting status/score displays.

#### M10 — Reports summary is hard-coded empty

- **Evidence:** `assessment_rows=0` and `assessment_status=[]` at `reports_v1.py:508-555`, while assessment export rows exist at `reports_v1.py:956-976` and production has four attempts.
- **Failure/risk:** summary and export disagree.
- **Affected:** HR and reporting users.
- **Severity:** medium.
- **Enterprise blocker:** no for scoring; yes for a complete Reports-parity claim.
- **Smallest remediation:** compute canonical attempt, distinct application, and status metrics.
- **Leave unchanged:** misleading zero/empty assessment reporting.

#### M11 — Live battery approval provenance is incomplete

- **Evidence:** active global battery is selectable by `is_active`; beta approval is only JSON status (`app.py:28429-28494`); production active battery has no explicit approval actor/time and one content version has null `created_by_user_id`.
- **Failure/risk:** the owner cannot prove who approved the definition for assignment or optional Ranking.
- **Affected:** product owners, HR, auditors.
- **Severity:** medium.
- **Enterprise blocker:** yes for assessment-influenced Ranking governance; no for controlled fixed-bank scoring.
- **Smallest remediation:** record approval actor/time/purpose in the existing policy/release metadata.
- **Leave unchanged:** unverifiable content governance.

#### M12 — Seed changes do not advance the frozen content version

- **Evidence:** startup updates seeded batteries/items at `app.py:28338-28426`, then freezes at `app.py:2835-2839`; freeze inserts the unchanged battery `content_version` at `assessment_service.py:110-133`.
- **Failure/risk:** changed content produces a new digest but can collide with the existing version uniqueness constraint and fail startup.
- **Affected:** deployment/content-release operators; new assessment sends after a bank update.
- **Severity:** medium.
- **Enterprise blocker:** no for the unchanged current bank; yes before any fixed-bank content update.
- **Smallest remediation:** fail release validation with a clear message unless the content version is explicitly incremented; do not auto-mutate old snapshots.
- **Leave unchanged:** a future content edit can cause an avoidable deployment failure.

### Minor defects

| Finding | Evidence | Risk / affected users | Severity | Blocker? | Smallest remediation | Leave unchanged |
|---|---|---|---|---:|---|---|
| Save error has no explicit retry/restored question | `app.py:37063-37082` | Candidate must infer that reload is recovery | Low | No | Restore same question or show “Try again” | Avoidable abandonment/support |
| Refresh loses durable completion confirmation | completion revokes tokens at `app.py:29734-29740`; validation rejects completed at `assessment_service.py:235-247` | Candidate sees generic unavailable/completed state | Low | No | Return a safe submitted state for the same attempt | Confusion after successful submission |
| Progress/focus accessibility incomplete | `app.py:36952-37090` has status text but no progress ARIA value or focus transfer | Keyboard/screen-reader candidates | Low for English | No | Add progress semantics and focus management | Less accessible flow |
| Browser smoke still proves dead HMAC helpers, not live DB-token take | `smoke-test-browser-assessment.py:86-101`; live validation is `assessment_service.py:191-248` | Browser regression can pass while live token integration fails | Low because Cleanup-1 token tests exist | No | Replace HMAC fixture with the live token lifecycle | Misleading browser confidence |
| WhatsApp reminder mints another valid token without revoking earlier reminders | `app.py:30159-30201`; HR resend revokes at `app.py:30254-30262` | Multiple live links increase exposure surface | Low | No | Reuse or revoke prior reminder tokens | Extra valid links persist until terminal state/expiry |

### Operational/content issues

| Finding | Evidence | Risk | Action / consequence |
|---|---|---|---|
| “passed the v1 threshold” implies a canonical pass/fail decision | `app.py:28747-28754` | HR over-interprets a descriptive band | Use “qualified band” unless employer threshold is approved; unchanged wording may drive unsupported decisions |
| “Official deterministic score JSON” can be over-read as psychometric validation | dashboard copy at `App.tsx:5567-5569`; synthetic norms are explicitly labelled in report code | Determinism is mistaken for external validation | Clarify “system-calculated”; leaving it increases interpretation risk |
| Migrated attempts lack reconstructable delivery/token history | production has 4 attempts, 0 invitations/tokens; migration defaults delivery to pending at `ops/migrate-assessments-cleanup1.py:87-155` | Historical delivery cannot be proven | Preserve as disclosed legacy limitation; do not fabricate events |
| Required-assessment copy remains available | `App.tsx:5694-5705`, `App.tsx:6094`, `RankingEvidencePolicyPanel.tsx:16-48` | Optional contract can be misconfigured/presented as mandatory | Keep inactive under current contract; unchanged active use would violate B1/B2 |
| Product-2 competency compiler does not emit the live scoring schema | compiler uses `choice_points` at `assessment_ai_service.py:894-926`; live uses `choice_scores` and `competencies` at `app.py:28700-28708`, `app.py:28891-28900` | A future direct publish bridge would score incorrectly | No current action while publishing is disabled; make schema compatibility a mandatory pre-publish gate |

### Optional enhancements

- Dashboard bulk send.
- Assistant status/explain/resend/cancel tools.
- Dedicated HR mobile assessment management.
- Additional question types, free-text grading, proctoring, negative marking, or time limits.
- Separate post-assessment Ranking mode.

None is required to make the current fixed-choice optional workflow safe.

### Already sufficient / freeze

- deterministic scoring;
- immutable version-pinned attempts, scores, and reports;
- answer validation and concurrency control;
- one open attempt per application;
- token hashing, expiry, and revocation;
- tenant-scoped application binding;
- no lifecycle/hiring side effect;
- AI authoring isolation and production kill switch;
- missing/pending/expired/wrong-job assessment does not zero CV Ranking;
- no AI score authority.

### Unknown pending evidence

- required retention/deletion period;
- whether hiring managers need job-scoped result visibility;
- whether item-level answers require a stronger permission than report summaries;
- whether the active global battery has an external owner approval record not represented in this database;
- production provider delivery callback availability outside this repository.
- deployed database grants for immutable assessment content/score/report tables.

## Recommended remediation phases

These phases are evidence-driven and intentionally small.

### Gate 0 — Enforce the tenant module boundary

1. Resolve assessment mode to `unused` before Ranking loads/components/presentation whenever the tenant module is off.
2. Remove assessment joins, columns, metrics, exports, and wording from all normal Reports paths module-off.
3. Gate Assistant tool visibility as well as execution.
4. Apply the canonical module check to public cancel and do not serve the branded public shell module-off.
5. Omit assessment permissions, policy controls, drawer/Overview/Ranking copy, mobile capability keys, and timeline labels from normal non-admin surfaces.
6. Preserve historical rows; on disable, mark only assessment-informed Ranking runs stale and never auto-recalculate.
7. Pass the two-tenant DOM/API/data-preservation qualification before other product expansion.

### Gate 1 — Restore the optional-assessment contract

1. At the existing Ranking integration boundary, make assessment `unused` unless an approved job evidence policy exists.
2. Require that policy to identify allowed battery/content version and normalization version.
3. Keep CV-only Ranking results intact and label any later assessment-informed run distinctly.
4. Remove optional candidates from “awaiting/need assessment” task/SLA presentation unless a policy or actual assignment requires action.
5. Mark only affected assessment-informed runs stale when the selected attempt completes, expires, is cancelled, or is superseded.
6. Recalculate only through the existing Ranking stale/recalculate authority.

No CV formula redesign.

### Gate 2 — Make assignment and bilingual delivery truthful

1. Pass existing actor/battery/locale/expiry fields through the production registry path.
2. Add terminal-state send guard.
3. Add explicit begin/privacy step.
4. Localize candidate chrome and set dynamic `lang`/`dir`.
5. Clarify multiple open application assessments in WhatsApp.

### Gate 3 — Close operational integrity gaps

1. Reconcile queued/pending invitations and lazy expiry.
2. Make “sent” semantics explicit or ingest provider delivery results.
3. Repair/derive the application projection from canonical tables.
4. Define retry lineage/selected attempt before allowing retries to influence Ranking.
5. Compute Reports assessment metrics from canonical attempt rows.
6. Require an explicit content-version increment before any seeded bank digest changes.

### Freeze after qualification

After these contained gates pass, freeze the fixed-bank scoring/runtime authority. Do not activate Product-2 production authoring until separately approved.

## Required schema/config changes

### Required for blockers

Prefer extending existing versioned Ranking policy metadata rather than adding a second formula authority:

```text
assessment mode: unused | supplementary
selected battery_key
selected assessment_version_id or allowed content SHA/version
selected norm_version
attempt selection rule
approved_by_user_id
approved_at
policy version
```

The existing `job_ranking_criteria_sets` approval/version/stale mechanism can hold this; a new table is not required unless product owners also want independent job assignment policy.

Set the effective default to:

```text
assessment = unused until explicit approval
assessment = unused whenever tenant module is disabled
```

Set Assessments as tool-call-gated in the canonical module catalog so Assistant discovery and execution share one entitlement boundary.

### Required only if retries are enabled as a governed product

Add or record:

```text
retry_of_attempt_id
retry_reason
authorized_by_user_id
authoritative_for_optional_ranking boolean or policy-selected attempt rule
```

### No schema change required

- Arabic UI localization;
- registry parameter/actor passthrough;
- terminal-state guard;
- explicit begin state;
- Reports count queries;
- delivery label correction;
- expiry reconciliation worker;
- application projection repair;
- Ranking stale invocation through the existing integration boundary;
- module-aware Reports queries/columns;
- module-aware UI/presentation copy;
- public cancel/shell entitlement checks;
- Assistant tool-discovery gating.

### Not justified now

- free-text answer tables;
- AI grading tables;
- proctoring/fraud tables;
- fixed assessment-weight redesign;
- separate assessment leaderboard tables.

## Local and staging qualification plan

### Mandatory ON/OFF tenant gate

Use two synthetic tenants with identical CV/job/candidate fixtures and one preserved historical assessment:

- Tenant A: `pre_hiring` + `assessments`;
- Tenant B: `pre_hiring` only.

For Tenant A, assert the module and permitted optional send are visible, while an unassigned candidate has no assessment task/SLA/warning and only assigned attempts appear in queue/Reports.

For Tenant B:

1. capture English and Arabic DOM/mobile snapshots for Overview, Jobs, Candidates, drawer, Ranking, Reports, Assistant, Settings, and assert zero case-insensitive assessment labels;
2. assert dashboard/public/Reports/action-registry reads and mutations return canonical disabled responses;
3. assert Ranking payload has no assessment component or missing code and CV-only values remain functional;
4. assert Assistant tool discovery and execution contain no assessment action;
5. assert general Reports headers, queries, and rows contain no assessment field;
6. compare attempt/response/score/report/event row counts before and after disable;
7. verify the preserved historical token cannot start, answer, or cancel;
8. verify no cross-tenant attempt/report/token access.

This gate is currently **failing/unproven**, not completed.

### Local/read-only gates

1. Deterministic report equality for all live item types.
2. Missing/unsent/pending/in-progress/expired/cancelled/wrong-job assessments:
   - candidate remains in pool;
   - CV-based score remains meaningful;
   - no assessment component exists;
   - no required/missing blocker copy.
3. No approved policy + completed assessment:
   - assessment component absent;
   - CV score/order unchanged.
4. Approved supplementary policy:
   - exact battery/version/norm/attempt provenance committed;
   - separately labelled result.
   - completion/cancel/expiry/supersession marks the affected run stale.
5. Concurrent sends/answers/final submits.
6. Terminal application send denied.
7. English/Arabic/mixed-content candidate snapshots at mobile widths.
8. Link preview does not start attempt.
9. Registry path preserves actor/battery/locale/expiry.
10. Reports attempt counts equal Assessments canonical queries.

### Staging gates

1. Synthetic tenant only; no real communication.
2. Email-only, WhatsApp-only, dual-channel, provider failure, and process interruption.
3. Resend revokes prior link.
4. Expiry sweep/read reconciliation.
5. Two applications sharing one phone require clarification.
6. Completed score survives live-bank edits and norm changes.
7. Retry cannot alter Ranking without explicit policy selection.
8. Cross-tenant attempt/report/token access fails.
9. Arabic owner UX with native devices and RTL.
10. Dashboard, Reports, Assistant, and Ranking show the same attempt/status identifiers.
11. Seed digest changes fail release validation unless `content_version` advances.

### Evidence already passing

- production deterministic assessment smoke;
- 4 Ranking evidence-policy unit tests;
- 92 Product-2 authority tests;
- 8 dashboard Ranking policy/presentation tests;
- dashboard `App.test.tsx` 6/6, including narrow module-off navigation/API suppression;
- entitlement hardening smoke;
- Assistant tool-call execution module-off smoke;
- production integrity counters: no mutable scores/reports, missing versions, version mismatches, duplicate open attempts, or orphan attempts.

These passing checks do not replace the mandatory two-tenant gate.

## Owner UX checklist

- [ ] Assessments page states “optional hiring evidence,” not a universal requirement.
- [ ] Queue shows actually assigned or policy-selected assessments only.
- [ ] No assessment does not display as candidate failure.
- [ ] CV Ranking remains available before any assessment.
- [ ] CV-only and assessment-informed Ranking are visibly distinct.
- [ ] Employer sees battery name, content version, locale, expiry, and purpose before send.
- [ ] Confirmation names candidate, application/job, channels, and assessment version.
- [ ] Terminal application sends require an explicit override or are blocked.
- [ ] Arabic page uses Arabic chrome, RTL, and correct numerals/punctuation.
- [ ] Candidate sees instructions/privacy before “Begin.”
- [ ] Candidate can recover from save/network failure without guessing.
- [ ] Completion confirmation remains understandable after refresh.
- [ ] HR sees accepted/sent/delivered/failed semantics accurately.
- [ ] Retry explains which result is authoritative.
- [ ] Report says deterministic/supporting evidence and does not imply automatic hire/reject.
- [ ] Assistant refuses unsupported status/explain/resend/cancel actions.
- [ ] Reports distinguish attempts from distinct assessed applications.
- [ ] Disabled tenant has zero assessment wording in non-admin English/Arabic DOM snapshots.
- [ ] Disabled tenant Ranking has no assessment component, policy source, or missing-evidence code.
- [ ] Disabled tenant Reports has no assessment column, join, metric, or export.
- [ ] Disabled tenant Assistant neither discovers nor executes assessment tools.
- [ ] Disabled tenant public links cannot start, answer, or cancel.
- [ ] Module disable preserves historical rows and only stales assessment-informed Ranking runs.

## Explicit out of scope

- redesigning the frozen CV Ranking formula;
- making Assessments mandatory;
- forcing every candidate to complete an assessment;
- preserving or adding a fixed 15-point weight as product policy;
- silently merging CV-only and post-assessment leaderboards;
- implementing code or schema;
- deploying;
- activating production AI authoring;
- adding free-text AI grading, proctoring, or fraud detection;
- redesigning Jobs, Candidates, Reports, Assistant, Interviews, Offers, or Post-Hire;
- beginning Interviews or another module.

## Final decision

Do **not** freeze the entire Assessments product yet. Freeze the deterministic scoring/version/token core, and remediate only the eight contained blockers:

1. explicit policy before Ranking consumption;
2. optional—not mandatory—queue semantics;
3. exact definition/version/attempt provenance;
4. qualified Arabic delivery;
5. stale invalidation through the existing Ranking authority;
6. module-off Ranking and Reports data isolation;
7. module-off product and Assistant invisibility;
8. public direct-URL fail-closed behavior.

Once those gates pass, the evidence supports freezing the fixed-bank Assessments runtime rather than expanding it.
