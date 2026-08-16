# Pre-Hiring Held Record Communication Authority — Remediation

**Status:** Contained **staging deploy + qualification complete**  
**Date:** 2026-07-25  
**Production deploy:** **not performed**  
**Classification flags / workers / tenants:** **unchanged**  
**SMS:** **no surface** (documented absent; not invented)

---

## Verdict

| Gate | Result |
| --- | --- |
| Held-record communication authority (staging) | **GO_STAGING** (qualify **35/35**) |
| Classification leave-state preserved (master OFF, workers OFF, `TENANTS=WATHEFNI`) | **PASS** |
| Production orchestrator untouched | **PASS** (authority module absent on production path) |
| Proceed to later classification production-dark packaging (from this gap only) | **GO** — this notify/authority hole is closed on staging |
| Production deploy of this authority patch or classification enablement | **NO-GO** (not in scope; stop condition met) |

**Stop condition met.** No production deployment. Classification packaging may proceed later with this remediation treated as a staging-qualified prerequisite for the held-notify gap.

---

## Root cause

UI / `held_allowed_actions` hid outreach for Talent Pool held rows, but **send helpers and HTTP/Assistant/bulk/offer paths had no shared live-application authority gate**.

Working-tree / staging `dashboard_prehire_notify` (and related helpers) could resolve by `app_key` and attempt dry-run notify for `needs_role` / `import_review` / `import_archived` and restricted / deletion-pending governance.

Canonical live SQL predicate already existed (`production_application_predicate` in `app.py`), but communication side effects did not enforce it + governance together.

---

## Authority contract

Pure module: [`wathefni-orchestrator/candidate_communication_authority.py`](wathefni-orchestrator/candidate_communication_authority.py)

Fail-closed before any transport / event / token / invitation / retry / batch residue when any of:

- held status: `needs_role`, `import_review`, `import_archived`
- governance restricted / deletion-pending / archive-active
- non-production `data_source` or test identity
- missing app/tenant context or tenant mismatch

Structured codes:

- `held_record_communication_forbidden`
- `restricted_record_communication_forbidden`
- `candidate_communication_requires_live_application`
- `candidate_communication_context_required`
- `candidate_communication_tenant_mismatch`

Authorized live Job applications continue under existing permissions, tenant checks, Job/lifecycle rules, channel policy, templates, and providers.

---

## Affected paths (gated)

**HTTP / helpers (`app.py` surgical staging patch):**

- dashboard notify / assessment / video (when invite send) / assessment resend
- `notify_candidate`, `send_email`, `candidate_communication_router`
- assessment send + invitation deliver
- interview invite / async video invite
- calendar schedule helpers
- CV validation notify
- company WhatsApp helper (including staging `audit_text` signature)

**Assistant / bulk (`action_registry.py` surgical staging patch):**

- notify / email / assessment / screening / video / interview / schedule executors
- batch preflight excludes held; all-held rejected; mixed batch skips held communication items; per-item re-check at execution

**Offers (`offer_service.py` surgical staging patch):**

- `send_offer` asserts live communication authority **before** delivery-operation claim / token / provider writes

**SMS:** no product surface — documented as absent.

---

## Artifact identity

| Field | Value |
| --- | --- |
| Source commit | `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2` |
| Allowlist artifact SHA | `a94c4178721b247201f5186817bd461a44b628cd95d0a187daf709ca50d1811e` |
| Evidence root | `/opt/wathefni/staging/staging-evidence/held-notify-authority/20260725T211236Z` |
| Qualify verdict | `GO_STAGING` (35 pass / 0 fail) |
| Backup root | `/opt/wathefni/backups/staging-pre-held-notify-authority-20260725T211236Z` |
| DB dump SHA | `cc4b8d6dc032b30d830ba372cdf064b67e9f4613fec925986f9f771047669ab4` |
| Baseline `app.py.pre` SHA | `b3388ebd480feb4e30215ba9b4bb4ee154ead11510e6ae2042e242d7f6c9c7a5` |
| Patched `app.py` SHA | `54f2be02ca9856a307d2946c5008c7d4d3cda248f60c343f2e2000281c6cad54` |
| Patched `action_registry.py` SHA | `b7992797bd6db01dd2461c3803e80089e10de91248cddaeecf1f8a2cba8d2bfb` |
| Patched `offer_service.py` SHA | `74c14abe376bbe6ddc322e64d58aa64270eeb948cb53dce252faa5e92c57162a` |
| Authority module SHA | `8a3949eac6d72c7f18514810171298615e1fded40e81afba2ee91239305aab53` |

### Changed-file allowlist (contained staging)

- `candidate_communication_authority.py` (new module)
- `test_candidate_communication_authority.py`
- Surgical patches (not full local overwrite of staging registry/offer):
  - `ops/patch-staging-app-held-notify-authority.py`
  - `ops/patch-staging-registry-held-notify-authority.py`
  - `ops/patch-staging-offer-held-notify-authority.py`
- Fixture alignment: `smoke-test-communication-router.py` (live-shaped candidate + held denial assertion)
- Ops: `ops/deploy-held-notify-authority-staging.sh`, `ops/held-notify-authority-staging-qualify.py`

**Important deploy lesson:** uploading the local full `action_registry.py` / `offer_service.py` broke staging (`clarify_first` / size divergence). Final deploy surgically patches the **staging baseline** and preserves staging APIs.

---

## Local proof

| Pack | Result |
| --- | --- |
| `test_candidate_communication_authority.py` + UC + classification units | **32 OK (1 skipped)** — app helper tests skip without local `psycopg2` |

---

## Staging qualification matrix (synthetic `HNSTG*` fixtures)

All held/restricted paths fail closed with **zero outbound delta**. Live Job application notify remains authorized under dry-run.

| Proof | Result |
| --- | --- |
| HTTP notify: `needs_role` / `import_review` / `import_archived` / restricted / deletion-pending | **PASS** (409 authority) |
| HTTP assessment held | **PASS** |
| HTTP video held | **PASS** (WATHEFNI `video_interviews` module disabled → 403 `module_disabled`, zero outbound) |
| Helper `notify_candidate` / router / registry executor held | **PASS** |
| Bulk split + batch preflight excludes held | **PASS** |
| Live notify + live helper authorized | **PASS** |
| Cross-tenant probe | **PASS** |
| Unit packs on staging venv | **PASS** |
| Zero synthetic residue | **PASS** |
| Classification workers still OFF / tenants `WATHEFNI` | **PASS** |
| Production authority module absent | **PASS** |

Evidence: `$EVIDENCE/held-notify-qualification.json`

---

## Frozen regressions

Core / plan packs (staging):

| Pack | Result | Notes |
| --- | --- | --- |
| `test_candidate_communication_authority.py` | **PASS** | |
| `test_unified_candidates.py` | **PASS** | |
| `test_talent_pool_classification.py` | **PASS** | |
| `smoke-test-communication-router.py` | **PASS** | after live-fixture fix |
| `smoke-test-canonical-recruiting-lifecycle.py` | **PASS** | |
| `smoke-test-tenant-isolation-harness.py` | **PASS** | |
| `smoke-test-jobs-phase2-stage-a-unit.py` | **PASS** | |
| `smoke-test-jobs-phase2-stage-b-unit.py` | **PASS** | |
| `smoke-test-offer-lifecycle.py` | **PASS** | |
| `smoke-test-assessments.py` | **PASS** | |
| `smoke-test-prehire-assistant-parity.py` | **PASS** | |
| `smoke-test-assistant-hr-reads.py` | **PASS** | |
| `smoke-test-interviews-remediation-unit.py` | **PASS** | |
| `smoke-test-module-catalog.py` | **PASS** | |
| Candidates **C0–C1** `candidates-c01-staging-matrix.py` | **PASS** | |
| Candidates **C2** `candidates-c2-staging-matrix.py` | **PASS** | |
| Candidates **C3** `candidates-c3-staging-matrix.py` | **PASS** | |

Known pre-existing / environment gaps (not introduced by this remediation):

| Pack | Result | Notes |
| --- | --- | --- |
| `smoke-test-jobs-phase1.py` | **FAIL** | publishability gate on incomplete smoke fixture (same class as prior UC report) |
| `smoke-test-interview-workflow.py` | **FAIL** | Meet-link string assert (pre-existing) |
| `smoke-test-dashboard-auth.py` / `entitlement-hardening.py` / `mutation-allowed-actions.py` | **FAIL** | staging host lacks `apps/wathefni-dashboard/src/App.tsx` |
| Ranking / Reports dedicated smoke packs | **missing** on staging host | not re-executed |

Final matrix artifact: `$EVIDENCE/frozen/matrix-final.json`

---

## Staging leave-state

```
wathefni-orchestrator-staging.service: active
environment_binding.match: true (staging DB)
WATHEFNI_TALENT_POOL_CLASSIFICATION=off
WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off
WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS=WATHEFNI
WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=on
WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI
WATHEFNI_DELIVERY_MODE=dry_run
production /opt/wathefni/orchestrator/candidate_communication_authority.py: ABSENT
```

Rollback: `/opt/wathefni/backups/staging-pre-held-notify-authority-20260725T211236Z/ROLLBACK.sh`

---

## Residual risks

1. **Local vs staging divergence:** local `action_registry.py` / `offer_service.py` carry authority gates but are not byte-identical to surgically patched staging trees (e.g. staging retains `clarify_first`). Future production packaging must use surgical patches or a reconciled tree — **do not** blindly rsync the local registry/offer onto production.
2. **Video HTTP path on WATHEFNI:** module entitlement disabled; fail-closed proven via `module_disabled` + zero outbound, not via authority 409 on that HTTP route. Helper/registry gates still cover video kinds when the module is enabled.
3. **SMS:** absent — no gate surface.
4. **Ranking / Reports** dedicated packs missing on this host; not a regression signal for this change.
5. App-level unit tests that need DB still skip in bare local Python (`psycopg2`); staging venv packs cover them.

---

## GO / NO-GO for later classification production-dark packaging

| Question | Answer |
| --- | --- |
| Is the held-record notify authority gap closed on staging? | **YES — GO_STAGING** |
| May classification production-dark packaging proceed from this gap’s perspective? | **YES — GO** (prerequisite satisfied on staging) |
| Deploy this authority patch or classification to production now? | **NO — NO-GO** |
| Touch classification workers / external tenants / Role Profiles? | **NO** |

**Stop.** Contained remediation complete; no production deployment.
