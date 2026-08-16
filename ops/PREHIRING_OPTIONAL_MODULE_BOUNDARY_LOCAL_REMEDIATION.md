# Pre-Hiring — Optional Module Boundary Local Remediation

**Scope:** optional module boundaries only. Live Interviews carved out as its own module, `video_interviews` narrowed to async recorded-answer interviews, public offer-link policy made explicit, and three small boundary fixes.

**Verdict:** local remediation complete, frozen, and green. 301 boundary gates pass across all four Interviews × Video Interviews combinations plus the Assessments navigation chip probe, zero residue, and zero regressions against the deployed production baseline.

**Frozen artifact:** `077103b2c4463470197e9c5fa44ebeb377b4aea86112fe5cb17d9b4d9b652af7`  
**Freeze record:** `wathefni-orchestrator/ops/OPTIONAL_MODULE_BOUNDARY_FREEZE.txt`  
**Source tree:** `/tmp/wathefni-c3-local`  
**Staging:** green on the same artifact (see `ops/PREHIRING_OPTIONAL_MODULE_BOUNDARY_STAGING_GREEN.md`).  

**Not promoted to production.** Staging completed in the ordered plan in section 10. No frozen module's behaviour was reopened: Jobs, Candidates, Ranking, Reports, Assistant, Assessments, Interviews, Offers/Hiring and the canonical hire authority all keep their existing semantics. What changed is *which module entitles which surface*, plus one Assistant presentation gate for Assessments.

---

## 1. Executive summary

Live interviewing previously had no module of its own. It shipped inside `pre_hiring`, and the Overview/queue surfaces that were supposed to gate it read:

```python
interviews_enabled=("interviews" in enabled_modules) or True
```

which is unconditionally `True`. A tenant could not turn live interviewing off, and the `video_interviews` module gated only the async recorded-answer flow while being treated in places as if it governed interviewing generally.

This remediation introduces the canonical module key `interviews` for live interviewing and leaves `video_interviews` owning async recorded-answer interviews only. The two are independently switchable. Every live-interview surface — routes, service writes, Assistant tools, Reports funnel/metrics/exports, Overview counts, work queue, mobile capabilities, dashboard navigation, Google Calendar/Meet sync — now resolves through a real entitlement. The unconditional `or True` is gone from the codebase.

Two defects were found and fixed during qualification that the ON/OFF matrix alone would not have surfaced:

1. **Assistant navigation advertised a dead Interviews page.** `dashboard_chat_artifacts` appended an "Open Interviews" chip whenever the operator's message contained "interview", "meeting" or "meet", with no module check. A tenant with both interview modules off would be offered a page that does not exist. Now gated on the page being reachable.
2. **A disabled module hung the whole dashboard.** `dashboardLoaded` waited on `interviews` being non-null. Once `loadInterviews` correctly stopped fetching for a disabled tenant, the readiness gate never satisfied and the entire workspace sat on a loading screen forever. Fixed by excluding a disabled module from the readiness gate, with a frontend regression test.

A third presentation leak — the Assistant "Open Assessments" chip — was left as a residual in the first pass and then fixed before freeze (section 6a). It is a module-boundary presentation fix only; Assessment scoring, delivery, and Ranking integration were not reopened.

A fourth finding is a deliberate design decision rather than a defect: `offer_service.load_offer_bundle` intentionally carries no `employment_offers` guard, because `respond_via_token` returns through it. Guarding it would revoke exactly the already-issued candidate links the approved policy exists to protect. HR-side offer reads are entitled at their entry points instead, which is proven at route level below.

---

## 2. Changed files

All SHAs are truncated to 12 hex characters. "Production" is the artifact currently deployed at `/opt/wathefni/orchestrator`, pulled read-only for comparison.

### Backend — product code

| File | Production | Local | Changed lines | What changed |
|---|---|---|---|---|
| `module_catalog.py` | `74e09aa59c86` | `2a1d4264343e` | 52 | New `interviews` module, `video_interviews` narrowed to async-only, aliases, bundle, legacy implication |
| `app.py` | `bd1c94eeb43e` | `6c237cab102f` | ~195 | Removed `or True`; re-pointed live-interview routes; record-scoped interview entitlement; kind-filtered payloads and counts; inner guards; Assistant Interviews + Assessments navigation gates |
| `action_registry.py` | `75274646eb81` | `d5d9b587f3ec` | 14 | Five live-interview `ActionSpec`s moved to `interviews`; priorities/work-queue executors read the real entitlement |
| `interview_service.py` | `8f10e8f74143` | `17e1a33d85ee` | 17 | `_require_live_interviews` service-level guard on `schedule_interview` |
| `offer_service.py` | `a4f691dec596` | `993c1bbdea97` | 37 | `public_offer_link_policy` + `PUBLIC_OFFER_LINK_ACTIVE_STATUSES`; policy enforced in `public_offer_preview`; documented why the shared bundle renderer stays unguarded |
| `reports_v1.py` | `d7f52f2a082f` | `52c7bade5335` | 460 | Module-owned funnel steps, metric catalog, export types and candidate export columns; module-aware SQL and headers in both locales |
| `operator_mobile.py` | `0fa299a11e0f` | `72c492297e1a` | 32 | Interview capabilities follow either interview module; keys omitted entirely when both are off |
| `operator_mobile_data.py` | `574e9f565c0f` | `aaccb47ea332` | 35 | Kind-filtered interview lists and details; both-off denial reports `module_disabled` rather than `action_forbidden` |

### Backend — tests

| File | Production | Local | Changed lines |
|---|---|---|---|
| `smoke-test-entitlement-hardening.py` | `8af7e296687c` | `70a2291daede` | ~42 |
| `smoke-test-module-catalog.py` | `2b16b08a4faf` | `391f2961b0f0` | 30 |
| `smoke-test-toolcall-orchestrator.py` | `92b3b7f77d22` | `30350c64a382` | 35 |
| `smoke-test-prehire-registry-parity.py` | `989df1c9eca1` | `c99ee7eba655` | 2 |
| `smoke-test-hr1-operator-mobile.py` | `e3b13008b9cc` | `903c2f396462` | 2 |
| `smoke-test-hr3-mobile-data.py` | `007a01cac6c7` | `b43a1e840bd6` | 2 |
| `smoke-test-mobile-action-authority.py` | `3e109b190ec6` | `54712691fb03` | 2 |

The last three each add `"interviews"` to a stubbed module set. Their assertions check interview capability behaviour, so their fixture tenant must actually have the interviews module; without that they were asserting on a tenant that no longer has interviewing at all.

### Frontend

| File | What changed |
|---|---|
| `apps/wathefni-dashboard/src/App.tsx` | `anyModules` nav ownership + `navItemModuleEnabled`; `liveInterviewsOn` / `videoInterviewsOn` / `interviewsPageEnabled`; module-aware `loadInterviews`; `InterviewsPage` tabs, metrics and agenda follow the two modules; `interviewsReady` excluded from the readiness gate when disabled |
| `apps/wathefni-dashboard/src/App.test.tsx` | Fixture names both interview modules explicitly; two new tests for both-off and video-off-only |

### New operational files

| File | Purpose |
|---|---|
| `ops/backfill-interviews-module-entitlement.py` | Additive, idempotent backfill granting `interviews` to every registry tenant that has `pre_hiring` |
| `ops/optional-module-boundary-matrix.py` | The four-combination boundary qualification matrix (301 gates, including Assessments chip ON/OFF) |
| `ops/optional-module-boundary-staging-matrix.py` | Staging wrapper (STBND* tenants, explicit allow flag) |
| `ops/local-boundary-regressions.sh` | Frozen-module regression sweep with per-suite exit codes |
| `ops/OPTIONAL_MODULE_BOUNDARY_ARTIFACT.sha256` | Frozen deploy artifact identity |
| `ops/OPTIONAL_MODULE_BOUNDARY_FREEZE.txt` | Per-file freeze manifest |

### Not part of this change

`_verify_posthire_prod.py` differs between the local checkout and production. It is pre-existing drift from an earlier post-hire task, is not in the deploy `CODE_FILES` list, and was not touched here. Recorded so the diff is not mistaken for remediation scope.

---

## 3. Module catalog and config delta

### New module

```python
ModuleDefinition(
    "interviews",
    "Interviews",
    "pre_hire",
    "candidate",
    25,
    toolcall_gated=True,
    depends_on=("pre_hiring",),
    recommended_with=("assessments",),
    recommendation_copy=(
        "Requires Pre-Hiring. Live interview scheduling, panels, feedback, agenda, and calendar sync. "
        "Independent of Video Interviews."
    ),
),
```

`video_interviews` keeps order 30, gains `toolcall_gated=True`, and its copy now states it is asynchronous recorded-answer interviews only. Neither module depends on the other: both declare `depends_on=("pre_hiring",)` and nothing else, which is what makes them independently switchable.

| Field | `interviews` | `video_interviews` |
|---|---|---|
| Owns | Live scheduling, physical/phone/manual-link, panels and interviewer assignments, feedback and scorecards, agenda/calendar, Google Calendar/Meet sync | Async recorded-answer interviews and their public candidate flow |
| `depends_on` | `("pre_hiring",)` | `("pre_hiring",)` |
| `toolcall_gated` | yes | yes |
| Order | 25 | 30 |

`hiring_assessment_suite` now bundles `("pre_hiring", "assessments", "interviews", "video_interviews")`. Aliases added for `interviews`: `interview`, `live_interview`, `live_interviews`, `interviewing`, `interview_scheduling` — every alias is unambiguously live so the two modules can never collapse into one another.

### Backward compatibility

Carving a module out of `pre_hiring` risks silently removing live interviewing from every existing tenant. Two mechanisms cover this, deliberately at different layers:

```python
LEGACY_IMPLIED_MODULES: dict[str, tuple[str, ...]] = {
    "pre_hiring": ("interviews",),
}
```

`apply_legacy_module_implications` runs only on the **seed-only** sources (company metadata and workspace config). The `company_modules` registry returns before it and stays authoritative, so an operator who turns `interviews` off is never overridden by an implication.

Registry-backed tenants — which is every real tenant — are covered by `ops/backfill-interviews-module-entitlement.py`. Verified locally against a copy of the staging tenant registry:

| Step | Result |
|---|---|
| Dry run | `pending_count: 11`, `inserted_count: 0` |
| Apply | `inserted_count: 11` |
| Re-run (idempotency) | `pending_count: 0`, `inserted_count: 0`, `already_present_count: 11` |
| `WATHEFNI` resolves `interviews` | `True`; `video_interviews` stays `False` (it never had that row) |
| Operator sets `interviews` off, backfill re-runs | `inserted_count: 0`, row reported under `already_present_disabled`, module stays **off** |

**The backfill is safe to run before the code deploy**, which removes any window where live interviewing could break. Under the deployed production code the only gates on the literal `"interviews"` key are the three `("interviews" in enabled_modules) or True` expressions, which are already unconditionally true, and `module_catalog_payload()` iterates the catalog so an unknown key renders nowhere. Verified empirically: the production baseline tree was run against the backfilled database and the setup-console payload still shows 12 rows with no `interviews` entry, and the full 136-suite regression sweep produced a byte-identical failure set to the same sweep against a non-backfilled database.

---

## 4. Entitlement map

### Live interviews → `interviews`

| Surface | Gate |
|---|---|
| `PATCH /dashboard/prehire/interviews/{id}` | `require_interview_record(..., "interview.manage")` |
| `POST /dashboard/prehire/interviews` (schedule) | `require_entitlement(context, "interviews", "interview.manage")` |
| Reschedule, notes, feedback submit, feedback reopen | `require_interview_record` / `require_interview_feedback_submission` |
| Agenda | `require_entitlement(context, "interviews", "prehire.read")` |
| `interview_service.schedule_interview` | `_require_live_interviews` (service-level, defence in depth) |
| Assistant tools | `schedule_interview`, `reschedule_interview`, `cancel_interview`, `send_interview_invite`, `get_interview_invite_status` → `module="interviews"` |
| Legacy action map | `schedule_candidate_meeting`, `schedule_interview`, `reschedule_interview`, `cancel_interview`, `send_interview_invite`, `get_interview_invite_status` → `interviews` |
| Overview counts, work queue, next action | `interviews_enabled="interviews" in enabled_modules` |
| Reports funnel step `interview`, `interviews` metric, `interviews` export type, candidate export `interview` column | `FUNNEL_STEP_MODULES` / `EXPORT_TYPE_MODULES` / `CANDIDATE_EXPORT_COLUMN_MODULES` |
| Google Calendar / Meet sync | inherited via `schedule_interview` |

### Async recorded-answer interviews → `video_interviews`

| Surface | Gate |
|---|---|
| `create_or_resume_async_video_interview` | inner `company_has_module(company, "video_interviews")` guard |
| Assistant tool `send_video_interview` | `module="video_interviews"` |
| Public async-video candidate flow | inherited from creation gate |

### Shared surfaces

The Interviews page, the mobile interview list, and the interview record endpoints serve both kinds. They resolve through:

```python
def require_interview_surface(context, permission) -> dict[str, bool]:
    """Denies with module_disabled only when neither module is enabled. Callers must
    still narrow their rows to the kinds that remain enabled."""
```

and `interview_record_module(row)` classifies each record as `video_interviews` when `interview_type` or `source` is `async_video`, otherwise `interviews`. `dashboard_interviews_payload` applies the resulting kind filter to the row list, the tab counts, and the feedback counts, so a disabled kind contributes no rows and no numbers.

### Unchanged authorities

Ranking's default evidence policy still reads `{"cv": "required", "screening": "optional", "assessment": "unused", "semantic": "optional", "interview": "unused"}`. The canonical accepted-offer hire gate and the atomic hire operation are untouched.

---

## 5. ON/OFF matrix

Six isolated synthetic tenants on a local-only Postgres whose runtime binding reports `application_environment: test`, `database_environment: test`, `match: True`. Delivery mode `dry_run` throughout. Every tenant carries an **explicit registry row** for both interview modules, so the matrix exercises real entitlements rather than the legacy implication.

| Tenant | `interviews` | `video_interviews` | Gates |
|---|---|---|---|
| `BND1` | ON | ON | 41 |
| `BND2` | ON | OFF | 42 |
| `BND3` | OFF | ON | 46 |
| `BND4` | OFF | OFF | 43 |
| `BNDH` | ON → both OFF → ON | history preservation | 46 |
| `BNDO` | ON | public offer-link policy | 54 |

Plus 9 catalog-contract gates, 6 Assessments-chip OFF-probe gates, and 2 cleanup gates. **301 gates, 0 failures, 12 recorded observations.**

`—` means the gate does not apply to that combination.

| Gate | BND1 | BND2 | BND3 | BND4 |
|---|---|---|---|---|
| Live scheduling works when `interviews` ON | PASS | PASS | — | — |
| Live scheduling blocked when `interviews` OFF | — | — | PASS | PASS |
| Async video works when `video_interviews` ON | PASS | — | PASS | — |
| Async video blocked when `video_interviews` OFF | — | PASS | — | PASS |
| Interviews API available when either ON | PASS | PASS | PASS | — |
| Interviews API blocked when both OFF | — | — | — | PASS |
| Assistant live tools follow `interviews` | PASS | PASS | PASS | PASS |
| Assistant video tool follows `video_interviews` | PASS | PASS | PASS | PASS |
| Reports funnel interview step follows module | PASS | PASS | PASS | PASS |
| Reports interview export type follows module | PASS | PASS | PASS | PASS |
| Mobile capability keys follow interview modules | PASS | PASS | PASS | PASS |
| No interview work-queue items when OFF | — | — | PASS | PASS |
| CV Ranking works regardless of interview modules | PASS | PASS | PASS | PASS |
| Offer pipeline unblocked by interview modules | PASS | PASS | PASS | PASS |
| Hire creates exactly one employee | PASS | PASS | PASS | PASS |
| Assistant nav offers Interviews only when reachable | PASS | PASS | PASS | PASS |

### Disabled-module absence, in the tenant's own words

`BND4` (both interview modules off) produced:

- Live scheduling: `{"error": "module_disabled", "required_module": "interviews"}`
- Async video: `{"error": "module_disabled", "required_module": "video_interviews"}`
- Interviews API: `module_disabled` with `required_module: interviews`
- Google Calendar sync: blocked (`InterviewAuthorityError`)
- Assistant visible live tools: `[]`; visible video tools: `[]`; all six tools deny with `module_disabled`
- Reports funnel: `['cv_received', 'ready_for_review', 'shortlisted', 'offer_sent', 'offer_accepted', 'hired']` — no interview step, no interview label
- Reports export types: `['candidates', 'roles', 'assessments', 'followups']`; requesting the `interviews` export raises `interviews_module_disabled`
- Candidate export headers, English: `Candidate, Phone, Email, Job, Stage, Screening, Assessment, CV received, Updated`
- Candidate export headers, Arabic: `المرشح, الهاتف, البريد, الوظيفة, المرحلة, الفرز, التقييم, السيرة مستلمة, آخر تحديث`
- Mobile capabilities: zero keys containing "interview", zero interview wording anywhere in the payload
- Mobile interview list: `module_disabled` with `required_module: interviews`
- Overview `enabled_modules`: `['assessments', 'employment_offers', 'pre_hiring']`; `features` reports `interviews_enabled: false, video_interviews_enabled: false`
- Overview action counts: `{"ready_for_review": 2, "assessment_pending": 1, "follow_up_needed": 0}` — no interview debt
- Assistant navigation for the message "please schedule an interview meeting": `pages=[]`

### Independent switchability

`BND2` scheduled a live interview while `video_interviews` was off and async-video creation was refused. `BND3` created an async video interview while `interviews` was off and live scheduling was refused. Record-scoped reads confirm the split: with one module off, the record owned by the disabled module 404s while the record owned by the enabled module reads normally.

### Ranking, Offers and Hiring stay non-blocking

In all four combinations Ranking produced a run over 2 items, the offer pipeline completed draft → approve → send → candidate accept, `enforce_hire_gate` returned `ok: true, required: true`, and the hire produced exactly one employee with the application at `hired`. No interview module state changed any of it.

### Historical record preservation

`BNDH` created 2 live and 1 async-video interview with both modules on, then both were switched off.

| Check | Result |
|---|---|
| Rows on disk before / after | `{video: 1, live: 2}` / `{video: 1, live: 2}` — unchanged |
| Interviews surface after disable | `module_disabled`, `required_module: interviews` |
| Direct record read after disable | `module_disabled` — preserved but not exposed |
| Reports funnel after disable | interview step absent; preserved history contributes nothing |
| Re-enable both modules | history returns intact and readable |

### No fake interview debt

With `interviews` off, the work queue contained no interview items and the Overview action counts contained no interview key. A candidate with no interview is never reported as missing evidence.

---

### Disabled Assessments chip (presentation-only)

| Gate | Result |
|---|---|
| assessments ON → tool-driven "Open Assessments" chip may appear | PASS on every combo tenant |
| assessments ON → message wording alone does not invent an Assessments chip | PASS |
| assessments OFF → zero Assessments page/chip/label/link even when `send_assessment` / wording fire | PASS |
| assessments OFF → Interviews navigation unchanged for live+video ON tenant | PASS |
| assessments restored → Assessments chip returns | PASS |

---

## 6a. Assessments chip fix (pre-freeze)

`dashboard_chat_artifacts` now mirrors the Interviews reachability gate:

```python
assessments_page_reachable = "assessments" in enabled
# ...
if assessments_page_reachable and tool in {"send_assessment", "execute_candidate_workflow"}:
    navigation.append({"type": "page", "page": "assessments", "label": "Open Assessments"})
```

No wording-only Assessments chip is added when the module is on (preserving prior behaviour). When the module is off, neither tool output nor message wording can suggest or link to Assessments. Assessment scoring, delivery, Ranking integration, and hire authority were not touched.

Locked by `smoke-test-entitlement-hardening.py` (`assessments_page_reachable`) and by the boundary matrix gates above.

---

## 6. Public offer-link policy

### The policy

Recorded verbatim in `offer_service.py` at the point of enforcement:

```python
# Approved policy: disabling Employment Offers is an HR-side entitlement change, not
# a candidate-facing revocation. A link already delivered to a candidate stays honoured
# until the offer itself reaches a terminal state, because silently killing a live offer
# a candidate is mid-way through responding to is worse than serving it. HR reads and
# mutations still fail closed, and token, expiry, and revocation checks are unchanged.
# Revocation remains an explicit HR act (withdraw or resend), never a side effect.
PUBLIC_OFFER_LINK_ACTIVE_STATUSES = frozenset({"sent", "accepted", "declined"})
```

**Disabling Employment Offers does not revoke an already-sent valid offer.** Turning the module off stops HR from reading or creating offers; it does not reach out and cancel an offer a candidate is currently deciding on. Revoking an issued offer stays an explicit HR act — withdraw, or resend which rotates the token — and never a side effect of an entitlement change.

`public_offer_link_policy(module_enabled, offer_status)` returns `{servable, reason, module_enabled}` so the decision is inspectable rather than implied, and the reason is surfaced to the caller as `link_policy` on the preview.

### Policy matrix

Evaluated with `module_enabled=False` for every offer status:

| Status | Servable | Reason |
|---|---|---|
| `draft` | no | `module_disabled` |
| `pending_approval` | no | `module_disabled` |
| `approved` | no | `module_disabled` |
| `sent` | **yes** | `issued_before_module_disabled` |
| `accepted` | **yes** | `issued_before_module_disabled` |
| `declined` | **yes** | `issued_before_module_disabled` |
| `withdrawn` | no | `module_disabled` |
| `expired` | no | `module_disabled` |

A never-issued offer is not reachable through the public path, and a terminal offer stops being reachable — so the exception is exactly "already delivered and not yet finished", nothing wider.

### Proof

`BNDO` sent an offer, then `employment_offers` was switched off.

| Gate | Result |
|---|---|
| Preview while module ON | full offer served |
| HR read route `GET /dashboard/prehire/offers/{offer_id}` while OFF | `403 module_disabled` |
| HR read route `GET /dashboard/prehire/applications/{app_key}/offers` while OFF | `403 module_disabled` |
| HR mutation (`create_draft`) while OFF | `OfferAuthorityError: Employment offers module is not enabled for this company.` |
| Issued candidate link while OFF | served, `link_policy: {servable: true, reason: "issued_before_module_disabled", module_enabled: false}` |
| Candidate accept via issued link while OFF | succeeded, offer reached `accepted` |
| Invalid token while OFF | `OfferAuthorityError: Offer link is invalid.` — token protection unchanged |
| Second, unrelated offer driven to `expired`, then previewed | `410 This offer has expired.` |
| Scope of surviving link | `offer_id` matches the one offer; the unrelated offer id and the unrelated `app_key` appear nowhere in the payload |
| Privacy shape of surviving link | company-scoped; no `hr_notes`, no `internal_notes`, no approval metadata |

The candidate's own compensation (`base_salary`, `allowances`) does appear in their own preview, which is correct — it is their offer. What must not leak is another candidate's record or HR-internal fields, and neither does.

### Where the read guard lives, and why

`load_offer_bundle` deliberately has **no** `employment_offers` guard, and now says so in its docstring. `respond_via_token` returns through it, so guarding it would revoke exactly the issued candidate links this policy protects. HR-side reads are entitled at their entry points instead: every route in `offer_routes.py` calls `_require_offers_module(context)` first, and the mobile candidate detail path checks `employment_offers_enabled` before loading offers. Both are proven blocked above at route level rather than asserted in prose.

---

## 7. Small boundary fixes

**Assistant tools hidden when their module is disabled.** Tool ownership is now split cleanly, verified by enumerating the registry:

| Tool | Module |
|---|---|
| `schedule_interview`, `reschedule_interview`, `cancel_interview`, `send_interview_invite`, `get_interview_invite_status` | `interviews` |
| `send_video_interview` | `video_interviews` |
| `send_assessment` | `assessments` |

Both modules are in `TOOLCALL_GATED_MODULES`. Tool visibility and execution entitlement were checked independently in all four combinations: a disabled module's tools are absent from the schema *and* denied on execution with `module_disabled`, so an operator can neither see nor invoke them.

**Reports omit disabled interview and offer labels, stages and exports.** `FUNNEL_STEP_MODULES` maps `interview → interviews`, `offer_sent → employment_offers`, `offer_accepted → employment_offers`. A disabled module contributes no funnel step, no label, and no conversion percentage — so the funnel does not silently show a 0% conversion through a stage the tenant does not have. `EXPORT_TYPE_MODULES` and `CANDIDATE_EXPORT_COLUMN_MODULES` remove disabled export types and columns, in English and Arabic, and `_assert_export_type_enabled` refuses a disabled export type outright.

**Inner module guards on creation services.** `create_or_resume_assessment_attempt` returns `{"ok": false, "error": "module_disabled", "required_module": "assessments"}`; `create_or_resume_async_video_interview` raises `403 module_disabled` naming `video_interviews`; `interview_service.schedule_interview` calls `_require_live_interviews`. Routes and registry specs were already entitled — these guards mean a *new* caller cannot write against a disabled tenant by forgetting the outer check.

**Plus the two defects found during qualification** (Assistant navigation chip, dashboard readiness gate), described in section 1.

---

## 8. Tests

### Boundary matrix

`ops/optional-module-boundary-matrix.py` — **301 gates, 0 failures, verdict PASS.** Evidence: `wathefni-orchestrator/reports/optional-module-boundary-matrix.json`. The matrix refuses production always, and refuses staging unless `WATHEFNI_BOUNDARY_ALLOW_STAGING=1` (used only by the staging wrapper).

### Frozen-module regressions

`ops/local-boundary-regressions.sh` runs all 136 suites (122 smoke tests, 14 pytest suites) and records every exit code. The honest way to read this is a before/after comparison, so a pristine tree was built by restoring the 12 changed backend files to their exact production SHAs and the same sweep was run against the same database.

| Sweep | Failures |
|---|---|
| Production baseline | 26 / 136 |
| After remediation | 23 / 136 |
| **New failures introduced** | **0** |

Three suites that failed on the baseline pass after the remediation: `smoke-test-entitlement-hardening.py` and `smoke-test-dashboard-auth.py`, plus `test_candidates_c2_integration_contracts.py` (order-dependent).

The 23 shared failures are all environmental and identical on both trees:

| Cause | Suites |
|---|---|
| Refuses to run outside staging, or needs a staging token / ack env var | `assessments-cleanup1`, `prehire-overview-remediation`, `jobs-phase2-stage-a`, `jobs-phase2-stage-b`, `canonical-lifecycle-prod` |
| Needs a live HTTP server or live dashboard token | `real-interview-flow-live`, `video-interview-stage1-live`, `interview-workflow-live`, `notification-policy-live` |
| Missing optional local dependency (`sqlalchemy`, `psycopg2` package layout) | `hr0-legacy-recruiter-quarantine`, `interview-workflow` |
| Needs workspace files, backup history or seeded data absent locally | `backup-restore`, `browser-assessment`, `clean-dialog-manager`, `candidate-whatsapp-cleanup`, `dashboard-data-hygiene`, `context-guardrails`, `hr0-manager-scope-fail-closed`, `hr2a-mobile-data`, `payroll-hours`, `phase8c2-r1a` |
| Pre-existing stale assertion | `test_candidates_c01.py` asserts `create_candidate_interview_from_schedule` exists in `action_registry.py`; that symbol is absent from **production** too |
| No tests collected (needs `httpx2`) | `test_offers_hiring_local_remediation.py` |

Three suites did regress mid-remediation and were fixed rather than excused: `smoke-test-hr1-operator-mobile.py`, `smoke-test-hr3-mobile-data.py` and `smoke-test-mobile-action-authority.py` each stub a module set that lacked `interviews`, so their interview-capability assertions were running against a tenant with no interviewing. Adding `"interviews"` to those stubs restores the tests' original intent.

### Frontend

`npm test` — **76 tests across 19 files, all passing** (74 before, plus two new boundary tests). `npx tsc -b` exits clean.

New tests:

- *hides interviews and still finishes loading when both interview modules are disabled* — the regression guard for the readiness-gate bug. Asserts the workspace finishes loading, the Interviews nav button is absent, and no `/dashboard/prehire/interviews` request is made.
- *keeps live interviews when only the video module is disabled* — asserts independent switchability from the UI side.

### Static contract tests

`smoke-test-entitlement-hardening.py` now locks in the whole boundary so it cannot silently regress: no `("interviews" in enabled_modules) or True` anywhere; no interview mutation entitled through `pre_hiring`; `require_interview_record` and `enabled_interview_modules` exist; both creation-service inner guards present; `_require_live_interviews` present; `public_offer_link_policy` and `PUBLIC_OFFER_LINK_ACTIVE_STATUSES` present; `FUNNEL_STEP_MODULES` and `EXPORT_TYPE_MODULES` present; mobile denies with `required_module: interviews`; mobile capabilities read both modules; `interviews_page_reachable` and `assessments_page_reachable` gate Assistant navigation; `interviewsReady` keeps a disabled module out of the readiness gate; and the two new frontend tests exist by name.

`smoke-test-module-catalog.py` (50 checks) and `smoke-test-toolcall-orchestrator.py` cover the new module definition and independent tool gating.

### Cleanup and residue

The matrix removes every row it creates and asserts zero residue across 30 tables. Verified twice — once by the matrix, once by independent SQL after it finished:

```
companies=0 modules=0 apps=0 interviews=0 offers=0 employees=0 candidates=0
```

Eight generated offer documents were removed from disk. Zero cleanup errors.

---

## 9. Residuals

**1. ~~Assistant chat still offers an "Open Assessments" chip regardless of the assessments module.~~ Fixed before freeze** — see section 6a. `assessments_page_reachable` now gates the chip; wording alone never invents one; Interviews/video combinations remain unchanged.

**2. `_require_mobile_feature_action` reports an absent capability key as `action_forbidden`.** The interviews surface now pre-empts this with an explicit `module_disabled`, but the generic helper still degrades a missing key into what looks like a permission problem. Changing it would alter shared mobile behaviour for every workspace feature across all frozen modules, so it was left alone.

**3. `_verify_posthire_prod.py` drift.** Pre-existing, unrelated, not in the deploy file list. Left as-is.

**4. Local environment deviation.** The isolated local database was created from a staging schema dump, whose `wathefni_environment_identity` check constraint permits only `staging` and `production`. It was relaxed locally to also allow `test`. This is a guardrail for real environments and must not be part of any deploy.

**5. Local fixture drift during regression sweeps.** Some smoke tests delete `company_modules` rows for `WATHEFNI` as part of their own cleanup, which caused an early backfill dry run to under-report. Only affects the local fixture; the fixture was restored and the backfill re-verified. Both regression sweeps ran against the same drift, so the before/after comparison is like-for-like.

---

## 10. Staging plan

**Executed.** Staging-green artifact: `077103b2c4463470197e9c5fa44ebeb377b4aea86112fe5cb17d9b4d9b652af7`.

**Ordered execution (completed):**

1. Ran the inert `interviews` module-row backfill against staging while Offers/Hiring green `71dd4d10…` was still live (`inserted_count: 11`, then idempotent).
2. Verified the currently deployed artifact remained unaffected (old catalog lacked `interviews`, `or True` still present, service healthy).
3. Deployed the remediation artifact; aligned Reports/Interviews staging fixtures to entitle the modules their fixtures assume.
4. Ran `ops/optional-module-boundary-staging-matrix.py` — **301/301 PASS**, zero residue.
5. **Stopped before production.**

Details: `ops/PREHIRING_OPTIONAL_MODULE_BOUNDARY_STAGING_GREEN.md`.

**Rollback.** Code rolls back via the pre-deploy snapshot. The backfill rows do not need reverting — they are inert under the old code — but if a full revert is wanted, delete only rows where `module_key = 'interviews'` and `source = 'migration:interviews-module-carveout-v1'`, which leaves any operator-set row untouched.

---

## 11. Verdict

| Requirement | Status |
|---|---|
| Canonical `interviews` module for live interviewing | done |
| `video_interviews` narrowed to async recorded-answer only | done |
| Two modules independently switchable | proven in all four combinations |
| `("interviews" in enabled_modules) or True` removed | done, asserted statically |
| Disabled module: UI, APIs, Assistant, Reports, mobile, queues, public flows absent | proven |
| Enabled modules still work | proven |
| Historical records preserved, not exposed, restored on re-enable | proven |
| No fake interview debt | proven |
| Ranking, Offers, Hiring non-blocking | proven in all four combinations |
| Public offer-link policy implemented and documented | done, 8-status matrix proven |
| Assistant tools hidden per module | proven, visibility and execution |
| Assistant Assessments chip gated by `assessments` | done, ON/OFF proven |
| Reports omit disabled labels, stages, exports | proven, both locales |
| Inner guards on assessment and async-video creation | done |
| Frozen regressions pass | 0 new failures vs production baseline |
| Frontend tests + typecheck | 76/76 + clean tsc |
| Cleanup leaves zero residue | proven twice |
| Exact local tree frozen | `077103b2c4463470197e9c5fa44ebeb377b4aea86112fe5cb17d9b4d9b652af7` |
| Staging ON/OFF matrix | 301/301 PASS, zero residue |
| Production | **stopped — not promoted** |

Tree is frozen and staging-green. Production remains stopped pending owner approval.
