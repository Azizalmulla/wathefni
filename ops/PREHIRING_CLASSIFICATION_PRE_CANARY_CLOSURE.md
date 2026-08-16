# Pre-Hiring Classification Pre-Canary Closure

Date: 2026-07-26 (UTC+3)  
Scope: the two limited frozen matrices and the two documented classifier-quality risks only  
Evidence root: `/opt/wathefni/staging/staging-evidence/classification-pre-canary-closure/20260725T220013Z`

## Verdict

**GO — for a separate, guarded internal `WATHEFNI` production canary phase.**

This is not authorization to toggle production now. Before a canary flag is enabled, the exact
staging-qualified classifier artifact must first replace the older production-dark classifier
while every production classification flag remains OFF, and its hash and dark invariants must be
reproved.

Current production remains dark:

- master: OFF
- tenant allowlist: empty
- schema execution flag: OFF
- manual execution: OFF
- workers: OFF and inactive
- UI: OFF
- classification runs, suggestions, review events, jobs, and tenant taxonomy nodes: all zero
- production classifier remains unchanged at
  `827e92cda2754a6d90f1aefce96f125cc725c385ab9241b07fb388d529628fe7`
  (`classifier.deterministic_v1.1`)

The staging-qualified candidate is:

- classifier version: `classifier.deterministic_v1.2`
- SHA-256: `d97bae99e9d181daaadd384e070951902fa35243d14c92776bd20b712de0505b`
- staging qualification: 106 PASS / 0 FAIL
- staging workers: OFF and inactive

No production classification tenant was enabled. No production classification worker was started.

## Scope compliance

Changed:

- synthetic matrix entitlements and company/job fixtures
- classifier evidence weighting for broad Technology
- token-boundary evidence matching
- classifier quality tests and staging qualification fixtures
- deterministic dry-run matrix environment
- exact synthetic cleanup checks

Not changed:

- Interviews authority
- Job publishability authority
- Role Profiles
- ranking behavior
- Person Registry
- outreach
- Job assignment
- `intake_admit`
- recruiting lifecycle authority
- external-tenant enablement
- production classification flags
- production classification worker state

## A. Frozen matrix closure

### Candidates C0/C1

The original limitation was real but fixture-only: `C01PRD` had `pre_hiring` enabled but did not
have the `interviews` module required by the schedule path.

Fixture changes:

- added `interviews=true` only to the isolated `C01PRD` synthetic company
- left the cross-tenant probe without an added Interviews entitlement
- added `country='KW'` to the disposable companies

The country addition was required after the schedule gate became reachable: the matrix later
exercised atomic hire, whose existing legal-entity authority correctly refuses a synthetic company
with no country/default. This was another fixture prerequisite, not a production authority defect.

No Interviews or hiring authority code changed.

Final evidence:

- production C0/C1: 44 PASS / 0 FAIL
- staging C0/C1: 44 PASS / 0 FAIL
- `confirmed_schedule_succeeds`: PASS
- canonical stage advancement: PASS
- calendar failure does not advance: PASS
- atomic hire and rollback invariants: PASS
- cleanup: zero isolated-company residue

Evidence:

- `production-matrices/candidates-c01-rerun.json`
- `staging-frozen/candidates-c01-staging.json`

### Optional-module boundary

The synthetic Job was made deterministic against the existing publishability contract:

- the production wrapper patches only the frozen matrix's synthetic payload in memory
- the payload now carries an explicit canonical title and synthetic description
- the wrapper asserts `publish_blockers` before attempting the transition
- the dry-run regression environment supplies the required apply-channel configuration explicitly
- no required Job field, publishability rule, or transition authority was weakened

Final evidence:

- production optional-module boundary: 301 PASS / 0 FAIL
- staging optional-module boundary: 301 PASS / 0 FAIL
- all six synthetic Jobs reached `status=open`
- interview/video ON/OFF independence: PASS
- ranking, assessments, offers, hiring, reporting, Assistant, history, and token boundaries: PASS
- cleanup: zero residue and no cleanup errors

Evidence:

- `production-matrices/optional-module-boundary.json`
- `staging-frozen/optional-module-boundary-staging.json`

## B. Classifier quality closure

### Root cause

`classifier.deterministic_v1.1` treated every taxonomy alias match as strong evidence. Two details
caused the documented failures:

1. short aliases were matched as substrings, so the Technology alias `it` matched words such as
   `responsibilities` and `time`;
2. generic `software`, `IT`, or `engineering` text could directly create a High broad Technology
   suggestion without proving a technical role, education, project/employment contribution, or
   sustained technical skills.

That explains both the non-technical software-tool promotions and the forced High Technology result
for `long_unclear`.

### Tuning implemented

`classifier.deterministic_v1.2`:

- applies token boundaries to text alias matching;
- scores broad `fn.technology` through a dedicated evidence policy;
- accepts technical role-title evidence;
- accepts technical education evidence;
- accepts technical project/employment evidence;
- accepts multiple sustained technical skills;
- allows one technical skill only when work/project context supports it;
- preserves raw-CV-text evidence when structured facts are absent;
- treats HR-confirmed facts as stronger than extracted facts;
- keeps supported Technology as Medium when a clearly non-technical primary profile supplies the
  primary function;
- refuses to manufacture Technology from generic digital, business software, ERP, or HR-system
  mentions;
- attaches the support category and quote to every broad Technology suggestion.

No CV-length threshold was added. No candidate-quality judgment was added.

### Before/after examples

- Clear Technology
  - before: Technology High
  - after: Technology High (`0.82`), backed by Software Engineer, Computer Science, and technical
    skill evidence
- Common business software
  - before: Technology High
  - after: no Technology; the independently supported Excel skill remains
- Finance + ERP/software
  - before: Technology High + Finance High (`classified_multi`)
  - after: Finance remains; Technology removed
- HR + HR systems
  - before: Technology High + HR High (`classified_multi`)
  - after: HR remains; Technology removed
- Technology + Operations
  - before: Technology High + Operations High
  - after: Operations High + Technology Medium, preserving the evidence-backed secondary area
- Career changer into Technology
  - before: Technology High + Engineering High
  - after: Technology High remains, backed by developer bootcamp/project/internship evidence
- Short clear technical CV
  - before: Technology High
  - after: Technology High remains; no short-CV penalty
- `long_unclear`
  - before: Technology High, caused by substring alias matching
  - after: `unclassified` / `Insufficient evidence to classify`, with no forced suggestion
- Structured-fact gap with useful raw text
  - before: technical role/skills were present but broad Technology was absent
  - after: Technology is recovered from backend-developer, Python, SQL, and API text evidence

Before/after JSON:

- `staging-classifier/classifier-before.json`
- `staging-classifier/classifier-after.json`

## Complete staging classification matrix

All one-shot runs reported `ocr_triggered=false` and `workers_started=false`.

- clear Technology (`software`): `classified`, Clear evidence; Technology High
- HR: `classified`, Clear evidence; HR retained
- Finance: `classified`, Clear evidence; Finance retained
- non-technical common software tools: no Technology; Excel skill retained
- Finance using ERP/software: no Technology; Finance retained
- HR using HR systems: no Technology; HR retained
- Mechanical Engineering: `classified`, Clear evidence
- Sales: `classified`, Clear evidence
- Marketing: `classified`, Clear evidence
- Operations: `classified`, Clear evidence
- multidisciplinary Technology + Operations: `classified_multi`; Operations High and Technology
  Medium
- career changer into Technology: `classified_multi`; Technology and Engineering evidence retained
- short clear junior technical CV: technical classification retained
- long unclear CV: `unclassified`; no Technology and no High suggestion
- evidence-backed Medium fixture: `cautious`, Partial evidence; Technology Medium
- evidence-backed review fixture: `needs_review`, Needs HR review; Technology Needs review
- structured-fact gap with raw text: technical role/function/skills retained
- insufficient identity-only CV: `unclassified`
- Arabic technical CV: technical labels retained
- English CV: Sales & Marketing retained
- bilingual CV: Sales & Marketing retained

Outcome coverage:

- High: present
- Medium: present
- Needs review: present
- Unclassified: present
- multi-label: present

Human review and version behavior:

- HR-confirmed label survived reclassification
- HR-rejected label remained rejected
- identical input/version was idempotent
- new document/extraction versions created a new run
- review events survived the new run
- taxonomy-version change produced a different run identity

Evidence:

- `staging-classifier/qualification/outcomes.json`
- `staging-classifier/qualification/staging-qualification.json`

## Side-effect and UX proof

The staging qualification took protected-table snapshots before and after classification. Counts
and latest timestamps were unchanged for:

- positions
- application lifecycle events
- ranking runs and items
- outbound delivery events
- extraction cache, finalizations, leases, and runs
- embedding reindex events and runs
- semantic documents

Additional gates:

- all synthetic applications remained `needs_role` with no position assignment
- shortlist, hire, and `intake_admit` paths remained denied for the held fixtures
- held notify remained fail-closed
- classification run responses reported no lifecycle mutation and no worker start
- no classification notify route exists
- production classifier hash remained unchanged during staging qualification

Unified Candidates:

- staging `test_unified_candidates.py`: PASS
- local Candidates table/filter/App test files: 3 PASS, 13 tests
- classification remains decoupled from Unified Candidates authority
- no new dashboard component or layout change was introduced in this phase

## Frozen regressions

Local:

- classifier unit suite: 18 PASS / 0 FAIL
- local classification qualification: 60 PASS / 0 FAIL
- Unified Candidates classification UX: 13 PASS / 0 FAIL

Staging qualification packs, all PASS:

- `test_talent_pool_classification.py`
- `test_unified_candidates.py`
- `smoke-test-canonical-recruiting-lifecycle.py`
- `smoke-test-tenant-isolation-harness.py`
- `smoke-test-jobs-phase2-stage-a-unit.py`
- `smoke-test-offer-lifecycle.py`
- `smoke-test-assessments.py`
- `smoke-test-prehire-assistant-parity.py`

DB-bound frozen matrices:

- production C0/C1: 44 / 44 PASS
- staging C0/C1: 44 / 44 PASS
- production optional-module boundary: 301 / 301 PASS
- staging optional-module boundary: 301 / 301 PASS

There are no `LIMITED`, missing, skipped, or failed results in the closure evidence.

## Zero-residue proof

The first end-state audit caught one staging tenant taxonomy node because the harness cleanup used
an uppercase `LIKE '%TPC%'` pattern against the lowercase synthetic node ID. The cleanup was changed
to delete and verify the exact synthetic node ID, and the complete 106-gate qualification was rerun.

Final staging qualification cleanup removed:

- applications: 22
- candidates: 21
- classification runs: 23
- suggestions: 92
- review events: 2
- classification jobs: 23
- tenant taxonomy nodes: 1

Final direct database audit:

- production classification sidecar counts: all zero
- staging classification sidecar counts: all zero
- production C0/C1 and optional-boundary companies/applications: zero
- staging C0/C1 and optional-boundary companies/applications: zero
- synthetic tenant taxonomy nodes: zero

Evidence: `final-posture.json`

## Changed-file allowlist

Product classifier and tests:

- `wathefni-orchestrator/talent_pool_classification.py`
  - `d97bae99e9d181daaadd384e070951902fa35243d14c92776bd20b712de0505b`
- `wathefni-orchestrator/test_talent_pool_classification.py`
  - `66e42f9997af46bd4ed5dc6e64c0d0c1d53c7eea2532ddc49e6bed79bd7f63e7`

Test-harness / fixture only:

- `wathefni-orchestrator/ops/candidates-c01-production-matrix.py`
  - `acd6491e26c50cf8151be7d8183e56bba6b7d80d689b965a7a343b37f3aab375`
- `wathefni-orchestrator/ops/optional-module-boundary-production-matrix.py`
  - `57a49537a77d609241705916b0192752e516037ebb416710a5947655dac62d8c`
- `ops/talent-pool-classification-staging-qualify.py`
  - `e63dc1befee803a7268089b15b54a73b6766a913da2aaaa99f78743beb2c842e`
- `ops/run-talent-pool-classification-production-dark-regressions.py`
  - `0dbfba7d4591fb79df707dd0a5e1a531728d228891d33da0e361bd59fc50fe09`

Report:

- `ops/PREHIRING_CLASSIFICATION_PRE_CANARY_CLOSURE.md`

Allowlist manifest SHA-256:

- `410de3dfb1ca5b8e09993910ccdabaf0fcca941657467717c089ced2dcb9216d`

## Residual risks and next-phase gate

Out of scope and unchanged:

- the taxonomy still has some broad parent/child wording overlap, for example Software Engineering
  can also evidence the separate Engineering function;
- this phase did not implement Role Profiles, ranking integration, Person Registry, outreach, Job
  assignment, or lifecycle changes;
- no external tenant was qualified.

Required before the internal production canary:

1. deploy exact classifier SHA
   `d97bae99e9d181daaadd384e070951902fa35243d14c92776bd20b712de0505b`
   to production with all classification flags still OFF;
2. verify the deployed hash, health, empty sidecars, empty tenant allowlist, and inactive worker;
3. use a separately approved canary action to enable only internal `WATHEFNI`;
4. keep workers OFF unless a later phase explicitly qualifies and authorizes them.

Until step 1 is complete, toggling the current production artifact is **NO-GO**. The exact
staging-qualified artifact is **GO** for that next guarded canary phase.
