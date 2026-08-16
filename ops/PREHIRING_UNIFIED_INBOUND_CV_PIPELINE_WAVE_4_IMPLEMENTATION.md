# Pre-hiring Unified Inbound CV Pipeline — Wave 4 Implementation

Date: 2026-07-27 (Asia/Kuwait) / stamp `20260727T001021Z`  
Scope: Person Registry + Talent Pool authority + canonical owned CV versions + CK `person:`/`subject:` + exact Job binding + universal verified-job-binding gate  
Production mutations: **none**  
Production dual-write / Wave 4 flags: **OFF** (verified)  
Channel cutover: **no**  
External tenants: **not enabled**  
Role Profiles / post-hiring: **not started**  
Unified intake waves after this report: **stop**

Prerequisites accepted:

- Wave 0 / Phase 0 contract freeze
- Wave 1–3 implementations (accepted)

## Four major waves (status)

| Wave | Scope | Status |
|---|---|---|
| **0 / freeze** | Contract freeze | Accepted |
| **Wave 1** | Envelope + email dual-write + defect fixes | Accepted |
| **Wave 2** | Shared processing + `cv_version_id` dual-write | Accepted |
| **Wave 3** | Staging dual-write + Manual/WhatsApp adapters | Accepted |
| **Wave 4** | Person Registry / Talent Pool / CK person-subject / Job binding / universal gate | **This report — complete** |

## Executive verdict

| Gate | Result |
|---|---|
| Person Registry create/link via intake subjects (no unsafe merges) | **PASS** |
| Governed `talent_pool_entries` (CV-only non-actionable) | **PASS** |
| Identity-review without merge | **PASS** |
| Cross-channel duplicate prevention (exact phone/email reuse; ambiguous → review) | **PASS** |
| Person/subject-owned reusable `cv_versions` (no Ranking rewrite) | **PASS** |
| CK `person:` / `subject:` refs + `app:` compatibility | **PASS** |
| Held/provisional searchable + non-actionable | **PASS** |
| Identity correction invalidates chunks before reindex | **PASS** (contract) |
| Wave 1 `_anchor_actionability` preserved | **PASS** |
| Exact Job binding + consent + `application_job_bindings` / `application_cv_bindings` | **PASS** |
| CV-only remains Talent Pool; apps only after verified binding | **PASS** |
| `assert_verified_job_binding` shadow-deny first | **PASS** |
| Enforce mode lab-proven (not enabled on staging service) | **PASS** |
| Local suites | **112/112 PASS** |
| Real staging qualify | **23/23 PASS** |
| Health 200 staging + production | **PASS** |
| Production flags / drop-in untouched | **PASS** |
| No production channel cutover | **PASS** |

### GO / NO-GO

| Decision | Result |
|---|---|
| **WATHEFNI production-dark migration** (flags ON, dual-write only, no channel cutover, enforce OFF) | **GO — conditional** |
| Controlled channel cutover (email/WhatsApp/manual → envelope authority) | **NO-GO** |
| Enabling `WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE` in production | **NO-GO** |
| External tenant enablement | **NO-GO** |
| Role Profiles / post-hiring | **NO-GO** (out of scope) |

#### Conditional GO blockers for production-dark

1. Keep **shadow** gate only (`ENFORCE` unset) for at least one production-dark observation window.
2. Deploy surgically (modules + drop-in); **never** full `app.py` replace on hosts that carry staging-only modules.
3. Confirm live email path remains authoritative (Wave 1–3 dual-write posture unchanged).
4. Rollback plan: unset Wave 4 env flags / remove drop-in; schema is additive and safe to leave.

## Architecture delivered

```text
Email / Manual / WhatsApp adapters (Wave 3)
        │
        ▼
inbound_cv_intake envelope dual-write
        │
        ▼
inbound_cv_wave4.after_intake_receipt
   ├─ inbound_cv_person_registry  → persons / memberships / identity_review
   ├─ talent_pool_authority       → talent_pool_entries (non-actionable by default)
   └─ inbound_cv_processing       → person/subject-owned cv_versions

Exact Job confirm (HR / Stage B)
        │
        ▼
inbound_cv_wave4.promote_with_verified_job_binding
   ├─ intake_consent_events
   ├─ application_job_bindings (verified)
   └─ application_cv_bindings (pinned CV reuse)

Downstream Job workflows
        │
        ▼
verified_job_binding_gate.assert_verified_job_binding
   shadow_deny (default) → enforce_deny (lab / future)
```

### Modules

| Module | Role |
|---|---|
| `inbound_cv_person_registry.py` | Safe person/membership link; ambiguous → `identity_review`; never auto-merge |
| `talent_pool_authority.py` | Governed `talent_pool_entries`; actionable only when linked person+membership |
| `inbound_cv_processing.py` | Additive `person_id` / `subject_id` / `ownership_kind` on `cv_versions` |
| `inbound_cv_wave4.py` | Orchestration after intake + promote helper + gate facade |
| `job_binding_authority.py` | Consent + job/CV bindings + duplicate preflight |
| `verified_job_binding_gate.py` | Universal gate; shadow then enforce |
| `candidate_knowledge_wave4.py` | `person:` / `subject:` refs, Talent Pool actionability, invalidation helper |
| `candidate_knowledge_authority.py` | Parses person/subject when flag ON; preserves `_anchor_actionability` for `app:` |
| `inbound_cv_adapters.py` | Calls Wave 4 after Manual/WhatsApp receipts |

### Feature flags (default OFF)

```text
WATHEFNI_UNIFIED_INBOUND_CV_WAVE4
WATHEFNI_UNIFIED_PERSON_REGISTRY_DUAL_WRITE
WATHEFNI_UNIFIED_TALENT_POOL_ENTRIES
WATHEFNI_UNIFIED_CK_PERSON_SUBJECT_REFS
WATHEFNI_UNIFIED_JOB_BINDING_AUTHORITY
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE   # lab only; not set on staging service
```

Staging drop-in enables all of the above **except** `ENFORCE`.

## Local qualification

Command:

```bash
cd wathefni-orchestrator
.venv/bin/python -m unittest \
  test_unified_inbound_cv_wave4 \
  test_unified_inbound_cv_wave3 \
  test_unified_inbound_cv_wave2 \
  test_unified_inbound_cv_wave1 \
  test_unified_inbound_cv_phase0_contracts
```

Result: **112/112 OK**

Covered locally:

- Email/manual/WhatsApp adapter Wave 4 hooks (non-creating)
- Identity conflict → review, no merge
- Exact contact reuse / new person
- Talent Pool non-actionable CV-only
- CV version reuse + ownership dual-write
- Job binding requires confirmation
- Shadow deny → enforce deny
- Held Talent Pool shadow deny
- CK person/subject + app compatibility
- Chunk invalidation before identity reindex
- Cross-tenant person seed isolation
- Zero applications invented by promote path
- App evaluation gate hook marker present

## Real staging qualification

Host: `root@76.13.63.68`  
Service: `wathefni-orchestrator-staging.service` (`127.0.0.1:8011`)  
DB: `wathefni_staging` via `WATHEFNI_DATABASE_URL`  
Evidence: `/opt/wathefni/staging/staging-evidence/unified-inbound-cv-wave4/20260727T001021Z`  
Local copy: `ops/screenshots/unified-inbound-cv-wave4/20260727T001021Z/`

Deploy: `ops/deploy-unified-inbound-cv-wave4-staging.sh`  
Qualify: `ops/unified-inbound-cv-wave4-staging-qualify.py`  
Patcher: `ops/patch-staging-app-unified-inbound-cv-wave4.py`

### Staging matrix (23/23 PASS)

| Check | Result |
|---|---|
| `health_200` | PASS |
| `staging_env` | PASS |
| `modules_importable` | PASS |
| `staging_db_connect` | PASS |
| `person_registry_link` | PASS (`linked`) |
| `identity_review_no_merge` | PASS |
| `talent_pool_entry` | PASS (non-actionable) |
| `owned_cv_version` | PASS |
| `cv_version_idempotent` | PASS |
| `job_binding` | PASS |
| `shadow_deny` | PASS |
| `verified_allow` | PASS |
| `enforce_deny_lab` | PASS (env override only) |
| `ck_person_ref` / `ck_subject_ref` | PASS |
| `ck_non_actionable` | PASS |
| `zero_downstream_mutation` | PASS (candidates 97→97, apps 86→86) |
| `rollback_flag_off_skips` | PASS |
| `cross_tenant_isolation` | PASS |
| `gate_kill_switch_off` | PASS |
| `scale_idempotent_cv` | PASS (25 writes → 1 id) |
| `production_dual_write_untouched` | PASS |
| `staging_commit` | PASS |

### Production isolation (verified)

| Check | Result |
|---|---|
| Production health `:8010` | 200 |
| Staging health `:8011` | 200 |
| Production drop-in `unified-inbound-cv.conf` | **absent** |
| Production `WATHEFNI_UNIFIED_INBOUND_CV_WAVE4` | **absent** |

### Staging incident + recovery

First deploy attempt failed closed: `cv_versions` already existed without `person_id`, and indexes were created before `ALTER TABLE`. Automatic rollback restored health. Schema order fixed (`ALTER` then indexes); redeploy **23/23 PASS**.

## Downstream gate coverage

`assert_verified_job_binding` actions:

`ranking`, `screening`, `assessment`, `interview`, `communication`, `lifecycle_transition`, `shortlist`, `reject`, `offer`, `hire`, `ck_ranking_evidence`

Staging evaluation endpoint surgically patched with Wave 4 marker (`UNIFIED_VERIFIED_JOB_BINDING_GATE_WAVE4`). With shadow ON / enforce OFF, missing bindings are observed as `shadow_deny` without blocking live ranking. Enforce remains lab-only.

## Explicit non-goals (honored)

- No production channel cutover
- No external tenants
- No Role Profiles
- No post-hiring work
- Live email / WhatsApp / manual outcome paths remain authoritative
- Historical Ranking / application evidence not rewritten

## Recommended next step (outside this wave)

1. WATHEFNI **production-dark** enablement of Wave 4 flags with **shadow only**.
2. Observe shadow-deny rates before any enforce decision.
3. Separate later task for controlled channel cutover after dark observation.

**Wave 4 complete. Stop.**
