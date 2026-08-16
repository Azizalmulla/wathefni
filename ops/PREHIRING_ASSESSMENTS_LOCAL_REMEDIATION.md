# Pre-Hiring Assessments — Local Remediation

**Status:** CLOSED — local remediation complete (2026-07-24 Kuwait)  
**Source tree:** `/tmp/wathefni-c3-local` (authoritative assessment tree; do not mirror into older claw orchestrator)  
**Report path:** `claw/ops/PREHIRING_ASSESSMENTS_LOCAL_REMEDIATION.md`  
**Deploy:** None (local close-out only)  
**Frozen cores preserved:** deterministic scoring/runtime, production AI authoring kill switch, CV Ranking soft-weight formula (`assessment_evidence` weight remains 15.0 when explicitly selected)

**Close-out rule:** Staging/operational residuals below are **not** reasons to reopen local scope. Do not add more local work merely to eliminate every historical path. Next step is promote this exact tree to an isolated staging artifact and run the full Tenant ON/OFF matrix before production.

## Executive summary

Contained local remediation restores the approved product contract:

1. Ranking defaults to `assessment = unused` and only consumes assessment evidence under an approved, fully selected job policy.
2. Module-off fails closed in Ranking, Reports, Assistant discovery, public cancel, overview/mobile counts, and normal HR wording.
3. Module-on queues/SLAs are assigned-only (no unassigned pending work).
4. Registry send preserves actor/battery/locale/expiry and blocks terminal applications.
5. Candidate take flow requires Begin, supports EN/AR RTL, and clarifies multi-open WhatsApp roles.
6. Delivery states and Reports metrics are truthful; hard-coded empty assessment summary values are replaced.

## Root causes addressed

| Root cause | Evidence before | Contained fix |
|---|---|---|
| Default Ranking policy treated assessment as optional and auto-consumed latest completed same-job attempt | `DEFAULT_EVIDENCE_POLICY.assessment=optional`; `soft_component_scores` contributed without selection metadata | Default `unused`; require complete `assessment_selection`; match attempt to selection rule |
| Module-off still joined/consumed assessment evidence and exported assessment columns | Ranking/Reports had no module gate | `company_has_module` forces unused; Reports omit assessment fields/exports when off |
| Unassigned eligible candidates counted as assessment_pending with 72h SLA | `assessment_pending_predicate` matched `''\|pending` | Assigned-only statuses; SLA anchored to attempt `created_at` |
| Production registry send dropped battery/locale/expiry/actor | `_send_assessment_executor` only passed note | Pass-through kwargs + ActionSpec optional fields |
| Public cancel skipped module check; page auto-started | cancel had no module gate; state `start=True` on load | Module check on cancel; intro + Begin; neutral unavailable shell |
| Reports summary hard-coded `assessment_rows=0` | `reports_v1.py` stubs | Canonical attempt counts/status breakdown when module on |
| Assistant still offered assessment tools when module off | `assessments.toolcall_gated=False` | `toolcall_gated=True` |

## Changed files

### Orchestrator (`/tmp/wathefni-c3-local/wathefni-orchestrator`)

- `candidate_ranking.py` — default unused; selection gate; provenance; module-aware effective mode
- `ranking_result_presentation.py` — omit assessment-needed wording when unused; selection miss copy
- `prehire_overview.py` — assigned-only pending; module-off zero/omit; SLA on assignment time; definitions gated
- `reports_v1.py` — real assessment metrics; omit columns/sections when module off
- `module_catalog.py` — assessments `toolcall_gated=True`
- `action_registry.py` — send param passthrough; terminal application block
- `app.py` — Begin/locale/RTL public page; public cancel module gate; neutral unavailable HTML; WhatsApp multi-open clarify; send kwargs + terminal guard; delivery `send_accepted`; pass-band wording
- `assessment_lifecycle.py` — widen delivery/invitation status CHECKs for truthful send states
- `operator_mobile.py` — omit assessments capability key when module off
- `operator_mobile_data.py` — omit assessment pending from mobile totals when off
- Tests: `test_candidate_ranking.py`, `test_ranking_result_presentation.py`, `smoke-test-prehire-overview-unit.py`, `smoke-test-module-catalog.py`

### Dashboard (`/tmp/wathefni-c3-local/apps/wathefni-dashboard`)

- `src/components/RankingEvidencePolicyPanel.tsx` — default assessment unused; hide assessment source when module off
- `src/components/JobsForm.tsx` — pass `assessmentsEnabled`
- `src/App.tsx` — drawer/Settings/Overview/Ranking/Reports/Assistant gates
- `src/lib/recruitingLifecycle.ts` — no-assessment empty-hero copy
- Tests: `App.test.tsx`, `RankingEvidencePolicyPanel.test.tsx`, `rankingPresentation.test.tsx`

## Schema / config delta

Additive only (no destructive data changes):

```text
assessment_attempts.delivery_status CHECK widened to:
  pending | queued | sent | send_accepted | failed | intentionally_skipped | revoked | expired

assessment_invitations.status CHECK widened similarly
```

No new Ranking formula tables. Assessment supplementary use stores selection inside approved criteria-set metadata:

```text
metadata.assessment_selection = {
  battery_key,
  assessment_version_id,
  norm_version,
  attempt_selection_rule,   # selected_attempt_id | latest_matching_battery_version
  selected_attempt_id?,     # required when rule = selected_attempt_id
  approved_by_user_id,
  approved_at,
  policy_version
}
```

Effective Ranking default:

```text
assessment = unused
assessment = unused whenever tenant module is disabled
assessment contributes only when mode ≠ unused AND selection is complete AND attempt matches selection
```

## Module guard

Canonical tenant guard remains `company_has_module(company, "assessments")` / `require_entitlement(..., "assessments", ...)`.

Applied across:

| Surface | Behavior when off |
|---|---|
| Dashboard assessment routes | 403 `module_disabled` |
| Public state/answer/cancel | fail closed; cancel no longer mutates |
| Public GET shell | neutral “Link unavailable” HTML |
| Ranking | assessment forced unused; no contribution |
| Reports summary/export | omit assessment metrics/columns/export type |
| Overview counts/definitions/queue | `assessment_pending=0`; definition omitted |
| Assistant discovery | assessments tools not offered (`toolcall_gated`) |
| Assistant execution | still fails closed if invoked |
| Mobile capabilities/home | assessments key omitted; pending not totaled |
| HR UI copy | drawer/Settings/Overview/Jobs/Ranking gates |

Historical assessment rows are never deleted on disable.

## Ranking contract

- Soft weights unchanged: skills 30 / experience 25 / education 15 / assessment 15 / semantic 15.
- Default policy: assessment unused.
- Without approved selection: no assessment component, no assessment warning as mandatory missing evidence, no score/order change from assessment data.
- With complete selection and module on: contribution only if attempt matches selection rule and is completed/same job.
- Provenance when used: attempt id, battery, assessment_version_id, norm_version, selection rule, policy version, approver/time, `ranking_result_kind=cv_plus_approved_assessment`.
- Otherwise `ranking_result_kind=cv_based`.
- Labels intended for surfaces: **CV-based Ranking** vs **CV + approved assessment evidence**.

## Queue / SLA behavior

Before: eligible stage + empty/pending assessment status → pending count + 72h SLA + “awaiting assessment send”.

After:

- only assigned attempts in `pending|in_progress|expired` (or open + delivery failed);
- unassigned candidates produce no queue item, SLA, pending count, or warning;
- SLA age uses `assessment_created_at` (assignment/invitation time);
- module-off returns `assessment_pending=0` without querying assessment work into definitions.

## Send-path proof

`action_registry._send_assessment_executor` now passes:

- `requested_by` / actor from action or admin metadata
- `battery_key`
- `locale`
- `expires_days`
- note/message

ActionSpec optional fields include those keys.  
`app.send_assessment` accepts the same kwargs and rejects terminal statuses (`hired|rejected|withdrawn|closed`) before create/deliver.

No second send authority was introduced.

## Arabic / English candidate-flow proof

Public assessment HTML now includes:

- intro screen with Begin control;
- state load without auto-start (`start` only after Begin);
- EN/AR copy tables;
- dynamic `lang` / `dir` including RTL;
- neutral unavailable page for module-off/invalid links.

WhatsApp: multiple open attempts prompt role selection instead of silently choosing latest.

## Delivery-state contract

Provider accept is labeled **send accepted**, not delivered. Neither `send_accepted` nor legacy `sent` means the candidate opened or completed the assessment.

Supported states (DB + labels):

- queued
- pending
- send_accepted (authoritative HR send path after provider accept)
- sent (legacy CHECK-compatible value — **not** confirmed delivery; see below)
- failed
- intentionally_skipped
- revoked / expired (attempt-level)

### Legacy WhatsApp reminder `sent` path (documented residual)

One historical WhatsApp candidate-status / reminder path in `app.py` still writes invitation/attempt `delivery_status='sent'` (and event payload `status: sent`). This path is intentionally **left in place** for local close-out.

Staging rules for this residual:

- Treat `sent` as a **legacy label only**, never as confirmed candidate delivery.
- Owner-facing copy and qualification checks must use **Send accepted** semantics for the HR send path (`send_accepted`) and must not promote `sent` to “delivered.”
- Do not reopen local remediation solely to rewrite this historical path; fold any rename into a later staging/ops pass if needed.

Invitation recovery after interruption remains a residual operational item (see Staging / operational residuals).

## Reports parity

When Assessments enabled:

- `assessment_rows` counted from `assessment_attempts`
- `assessment_status` breakdown populated from attempt statuses
- distinct assessed applications available via attempt/application join path

When disabled:

- assessment summary fields omitted
- candidates export omits assessment column
- dedicated assessments export remains entitlement-gated

## Tenant ON / OFF matrix

| Assertion | Tenant ON (expected) | Tenant OFF (expected) | Local proof status |
|---|---|---|---|
| Module nav / dedicated page | Visible | Absent | UI unit: `App.test.tsx` |
| Optional send with permission | Available | Hidden + execution blocked | registry + UI gates; toolcall smoke |
| Unassigned candidate queue/SLA/warning | None | None | overview unit smoke |
| CV Ranking independent | Yes | Yes (assessment unused) | EvidencePolicy unit tests |
| Only assigned attempts in queues/Reports | Yes | N/A / omitted | overview predicate + Reports module gate |
| Approved supplementary selection | Contributes with provenance | Forced unused | selection unit tests |
| Zero assessment wording (non-admin) | Contextual only | Required | partial UI gates; full DOM snapshot suite still staging |
| Ranking ignores historical evidence | Only if selected | Always | unit |
| Mutations fail closed | Allowed with entitlement | All blocked | entitlement + public cancel |
| Historical rows preserved | Yes | Yes | no delete on disable (source) |
| Tenant isolation | Yes | Yes | existing cleanup/pagination suites (both-on) |

Full two-tenant synthetic ON/OFF snapshot + HTTP matrix remains the guarded staging gate (not executed against production).

## Test results (local)

Re-verified 2026-07-24 in `/tmp/wathefni-c3-local`:

| Suite | Result |
|---|---|
| `EvidencePolicyUnitTests` (6) | PASS |
| `test_ranking_result_presentation` (24) | PASS |
| `test_reports_v1` (12) | PASS |
| `smoke-test-prehire-overview-unit.py` | PASS |
| `smoke-test-module-catalog.py` (24 assertions) | PASS (assessments toolcall-gated asserted) |
| `smoke-test-entitlement-hardening.py` | PASS |
| dashboard `App.test.tsx` (6) | PASS |
| dashboard `RankingEvidencePolicyPanel.test.tsx` (2) | PASS |
| `smoke-test-assessments.py` / app-level DB checks | SKIP locally (`psycopg2` missing; staging gate) |

Note: soft-weight formula and scoring service fingerprints unchanged; Product-2 authoring kill switch untouched.

## Frozen-core fingerprints (post-remediation)

```text
75343310d3ccc7f1  assessment_service.py
d531133bb60d94fe  assessment_lifecycle.py
a0402526d847f3a7  assessment_ai_contracts.py
9b8a54f19d10da7d  candidate_ranking.py
8d2f3c9f10931e2d  ranking_result_presentation.py
6642a47db498c9cf  prehire_overview.py
d7f52f2a082ff1ad  reports_v1.py
74e09aa59c86e768  module_catalog.py
da56619cc8c40782  action_registry.py
03edc063c496a1f2  app.py
```

Integrity checks:

- `SOFT_COMPONENT_WEIGHTS.assessment_evidence == 15.0` unchanged
- default policy assessment is `unused`
- Product-2 authoring remains production-off by existing kill switch (untouched authority)

## Staging / operational residuals (out of local scope)

These remain valid and must be handled in staging/ops. They **do not** reopen local remediation:

| Item | Classification | Notes |
|---|---|---|
| Full two-tenant ON/OFF staging qualification | required staging gate | DOM snapshot + HTTP matrix against synthetic ON/OFF tenants |
| Cleanup qualification (`smoke-test-assessments-cleanup1.py` and related) | required staging gate | needs staging DB/env; not a local reopen |
| Pending invitation recovery | material residual | two-phase invite/send still needs idempotent recover worker |
| Legacy WhatsApp reminder path writing `sent` | documented residual | must **not** be treated as confirmed delivery during staging |
| Lazy expiry sweep | material residual | expiry still primarily on-access |
| `applications.raw_json.assessment` projection repair job | material residual | still non-authoritative; derive-on-read preferred later |
| Retry lineage / authoritative attempt relation | material residual | selection rule covers Ranking; no retry parent column yet |
| Browser smoke HMAC drift | minor residual | Cleanup-1 token tests remain primary |
| Seed content_version auto-bump on digest change | material residual | fixed-bank release hygiene |
| Complete bilingual owner QA on native devices | operational | Begin/RTL implemented; device QA staging |
| Assessment selection UI for battery/version in Jobs panel | optional enhancement | backend accepts selection; panel currently coerces incomplete optional→unused |

## Guarded staging plan (next step after local close-out)

1. Promote the **exact** `/tmp/wathefni-c3-local` remediation tree to an **isolated staging artifact** (no partial mirror into older claw trees).
2. Staging synthetic tenants:
   - `ASSESSON*` = pre_hiring + assessments
   - `ASSESSOFF*` = pre_hiring only, with one preserved historical completed attempt
3. Execute the complete Tenant ON/OFF matrix:
   - Assessments cleanup1 + pagination
   - Ranking evidence-policy + recalculate
   - Reports export ON/OFF
   - Assistant tool discovery/execution ON/OFF
   - Public GET/state/answer/cancel ON/OFF
   - Mobile capabilities/home payloads
   - DOM word-absence scan (EN/AR) for OFF tenant
   - Explicit check: `sent` / `send_accepted` never asserted as confirmed delivery
4. Confirm no automatic Ranking recalculation on module disable; only stale marking if assessment-informed runs exist under previous policy.
5. Confirm historical attempt/score/report row counts unchanged after disable/enable.
6. Production only after staging matrix pass + explicit approval.
7. Do not enable Product-2 production authoring.

## Explicit non-goals (honored)

- No redesign of deterministic scoring/runtime core
- No production AI authoring activation
- No reopen of frozen CV Ranking formula/weights
- No deploy from this close-out
- No sync/mirror into older `claw/wathefni-orchestrator` tree
- No additional local scope merely to eliminate every historical path
