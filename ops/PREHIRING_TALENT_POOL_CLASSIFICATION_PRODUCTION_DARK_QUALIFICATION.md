# Pre-Hiring Talent Pool Classification — Production-Dark Qualification

**Status:** Guarded production-dark packaging, deployment, rollback, redeploy, and qualification complete  
**Date:** 2026-07-25  
**Classification enabled tenants:** **none**  
**Classification execution / workers / UI / manual runs:** **OFF**  
**Unified Candidates:** master **OFF**, internal `WATHEFNI` tenant override unchanged  
**Production outreach used:** **none**

---

## Verdict

| Gate | Result |
| --- | --- |
| Production-dark classification artifact | **GO_PRODUCTION_DARK** |
| Held-record communication authority active in production | **PASS** |
| Production-dark proof | **42/42 PASS** |
| Rollback → health/schema proof → exact redeploy → requalification | **PASS** |
| Enable classification for internal production tenant `WATHEFNI` | **NO-GO** |

The dark artifact is deployed and healthy. Classification remains unavailable to every tenant. Enabling the internal canary is **not approved** by this report because two frozen production matrices remain limited by pre-existing fixture/entitlement gaps, and the staging classifier’s Technology-bias / `long_unclear` quality risks remain unresolved.

**Stop condition met:** no classification enablement, no workers, no backfill, no Role Profiles.

---

## 1. Final artifact identity

| Item | Exact value |
| --- | --- |
| Source commit | `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2` |
| Approved classification staging artifact | `052743494cbc47efed07e999913e8b8ddbf509124ea3f17efac76c467a3fa973` |
| Qualified held-authority staging artifact | `a94c4178721b247201f5186817bd461a44b628cd95d0a187daf709ca50d1811e` |
| **Final production-dark composite artifact** | `3c894921621fb6b6082e087340f421722718714c488cb4f10c21c482cb972d64` |
| Final `app.py` | `1117915731f51a569e77a068e6b06ee51c8a5d16b89dd3813596bc3febaf7028` |
| Final `action_registry.py` | `b7992797bd6db01dd2461c3803e80089e10de91248cddaeecf1f8a2cba8d2bfb` |
| Final `offer_service.py` | `74c14abe376bbe6ddc322e64d58aa64270eeb948cb53dce252faa5e92c57162a` |
| Authority module | `8a3949eac6d72c7f18514810171298615e1fded40e81afba2ee91239305aab53` |
| Classification module | `827e92cda2754a6d90f1aefce96f125cc725c385ab9241b07fb388d529628fe7` |
| Classification routes | `ea48e74681df25c0f20773a138c64c5c7c56f2956c3167e700320d974822d372` |
| Taxonomy pack | `320d0a1f5eb19413f66337f81df955eadfe0e843d190b6048af313669c10fbb1` |
| Evidence root | `/opt/wathefni/production-evidence/talent-pool-classification-dark/20260725T212737Z` |

The final composite identity was written to `CORRECTIVE-PREDEPLOY.txt` **before** the final production-compatible app byte was copied into production.

### Artifact provenance note

The approved `05274349…` classification artifact is the SHA256 of staging evidence file `tpc-allowlist2.sha256`, not the older `allowlist.sha256`. The qualified manifest contains:

```text
827e92… talent_pool_classification.py
ea48e7… talent_pool_classification_routes.py
320d0a… talent_pool_taxonomy_v1.json
c9afab… test_talent_pool_classification.py
15cae7… local-qualify-talent-pool-classification.py
d5d2b0… ops/patch-staging-app-talent-pool-classification.py
```

### Production compatibility correction

The first sealed composite (`9dc522…`) retained production’s older status-only notify/assessment route guards. The first read-only proof correctly found that those guards ran before the new shared route guard. No provider or outbound call occurred.

`patch-production-app-held-authority-compat.py` replaced only those two older guards with the qualified DB-backed `require_live_candidate_communication` call. The corrected app was re-sealed as final composite `3c8949…`, recorded, deployed, rollback-proven, redeployed, and requalified **42/42**.

---

## 2. Changed-file allowlist

### Production runtime

- `app.py` — surgical classification mount + shared communication authority
- `action_registry.py` — held Assistant/tool and normal/mixed bulk gates
- `offer_service.py` — authority before delivery claim/token/provider/status writes
- `candidate_communication_authority.py`
- `test_candidate_communication_authority.py`
- `talent_pool_classification.py`
- `talent_pool_classification_routes.py`
- `talent_pool_taxonomy_v1.json`
- `test_talent_pool_classification.py`
- `local-qualify-talent-pool-classification.py`
- `/etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf`

### Operational tooling / evidence

- `ops/deploy-talent-pool-classification-production-dark.sh`
- `ops/talent-pool-classification-production-dark-qualify.py`
- `ops/run-talent-pool-classification-production-dark-regressions.py`
- `wathefni-orchestrator/ops/patch-production-app-held-authority-compat.py`
- this report

Production dashboard assets were **not changed**.

---

## 3. Predeployment and backup evidence

| Item | Proof |
| --- | --- |
| Production health before deploy | **200** |
| Production service | active + enabled |
| Classification modules before deploy | absent |
| Held-authority module before deploy | absent |
| Classification worker process/unit | **0 / 0** |
| Classification drop-in before deploy | absent |
| Unified Candidates posture | master OFF; `TENANTS=WATHEFNI` |
| Staging classification artifact | `05274349…` |
| Staging held-authority artifact | `a94c417…` |
| Daily backup | `/opt/wathefni/backups/daily/20260725T212743Z` — SUCCESS |
| Contained backup | `/opt/wathefni/backups/production-pre-talent-pool-classification-dark-20260725T212737Z` |
| Production DB dump SHA256 | `c87ac4da0bbc8f268cd19073e84e9ba16e95ed1fd5ddb638f5beab1b2641c961` |
| Dump verification | `pg_restore --list` PASS, 1101 entries |
| Previous `app.py` SHA | `2938ab332693a4815a97f0b3d748f4e7a4ee2238ef677d74d9e5b3e2c73b304a` |
| Rollback artifact | `…/ROLLBACK.sh` |

The rollback script restores the previous production app/registry/offer/Unified Candidates bytes, removes classification + authority modules and the classification drop-in, and intentionally does **not** drop additive schema.

---

## 4. Final feature-flag posture

```text
WATHEFNI_TALENT_POOL_CLASSIFICATION=off
WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS=
WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA=off
WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL=off
WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off
WATHEFNI_TALENT_POOL_CLASSIFICATION_UI=off

WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=off
WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI
```

Proof:

- classification `allowed_tenants=[]`
- `enabled_for_company=false` for `WATHEFNI`
- no `company_feature_flags` table/override
- zero classification worker processes
- zero classification worker service units
- Unified Candidates `WATHEFNI` remains in `tenant_canary_override` mode
- staging hashes unchanged:
  - app `54f2be…`
  - registry `b79927…`
  - offer `74c14a…`

No external tenant was enabled.

---

## 5. Additive migration and empty-sidecar proof

Only additive schema and immutable global taxonomy definitions were applied.

| Table | Final rows |
| --- | ---: |
| `taxonomy_releases` | 1 |
| `taxonomy_nodes` | 43 |
| `taxonomy_tenant_nodes` | **0** |
| `candidate_classification_runs` | **0** |
| `candidate_classification_suggestions` | **0** |
| `candidate_classification_review_events` | **0** |
| `talent_pool_classification_jobs` | **0** |

The global release/nodes are taxonomy definitions, not tenant assignments. There was:

- no taxonomy tenant assignment
- no classification run
- no suggestion
- no HR review event
- no queue claim/job
- no historical backfill

The artifact contains no queue claim implementation (`SKIP LOCKED` absent), workers are OFF, and the queue is empty.

---

## 6. Production-dark proof — 42/42 PASS

Evidence: `production-dark-qualification.json` and `REDEPLOY-QUALIFICATION.log`.

Key results:

- health **200** and production DB binding matched
- every classification flag OFF
- no tenant enabled
- functional taxonomy and run routes fail closed with 404 `talent_pool_classification_disabled`
- the status endpoint reports dark (`enabled_for_company=false`)
- no classification UI markers in production static assets
- dashboard asset tree SHA unchanged: `c7b8b954a48f14c2c3c03d4c7e330772259a4527a53fe6c612524868dbc91e02`
- classification tables present additively and execution sidecars empty
- no OCR, extraction, embedding, or semantic-document rerun since deployment
- no classification queue claim path
- Unified Candidates internal canary unchanged

### Existing production data remained unchanged

| Authority table | Predeploy | Final |
| --- | ---: | ---: |
| applications | 17 | 17 |
| candidates | 20 | 20 |
| positions / Jobs | 11 | 11 |
| application lifecycle events | 2 | 2 |
| outbound delivery events | 713 | 713 |

Regression matrices used only marker-scoped synthetic tenants with process-local dry-run delivery and returned to the exact baseline above.

---

## 7. Held communication authority proof

The production safety gate is active even while classification is dark.

| Proof | Result |
| --- | --- |
| `needs_role` | fail closed |
| `import_review` | fail closed |
| `import_archived` | fail closed |
| restricted governance | fail closed |
| tenant mismatch | fail closed |
| direct dashboard notify route | 409 shared authority before registry/provider |
| Assistant/tool notify executor | fail closed; router not called |
| generic helper/router/email/WhatsApp | provider mocks not called |
| normal/mixed bulk | qualified registry gate deployed |
| offer send | gate precedes delivery claim/token/provider |
| valid live application | authority allowed; existing policy/provider behavior tested with provider mocked |
| outbound residue | zero delta |

Proof used production code with synthetic in-memory rows and mocked providers. It did **not** send to a real candidate and did not create a production fixture.

---

## 8. Frozen production regressions

Evidence: `frozen-production-regressions-final.json`.

| Surface | Result |
| --- | --- |
| Classification units | PASS |
| Unified Candidates | PASS |
| Candidates C0–C1 | **LIMITED — 21/22** |
| Candidates C2 | PASS |
| Candidates C3 + read-only audit | PASS |
| Jobs Stage A / B | PASS |
| Ranking R0–R3 + presentation | PASS |
| Reports | PASS |
| Assistant A0–A3 + Jobs/Ranking UX | PASS |
| Interviews | PASS |
| Offers/Hiring | PASS |
| Assessments | PASS |
| Canonical lifecycle | PASS |
| Inbound email | PASS |
| Bulk intake | PASS |
| Tiered intake | PASS |
| Communication router | PASS |
| Tenant isolation | PASS |
| Permissions / optional-module boundary | **LIMITED — 12/13** |
| Dashboard | PASS — 13 files / 57 tests |
| HR mobile | PASS — 11 files / 44 tests |

### Known limited packs

1. C0/C1 `confirmed_schedule_succeeds` is blocked because the isolated matrix tenant does not enable the `interviews` module. This is the same fixture-entitlement class documented before this deployment.
2. Optional-module boundary reaches the pre-existing Job publishability guard because its synthetic Job is incomplete.

Neither failure touches classification code, flags, schema, or data. Both matrices cleaned to zero residue.

### Operational cleanup note

One Assistant Jobs/Ranking run initially inherited no systemd model pin and stopped on `voyage-4` vs required `voyage-4-large`, leaving its marker-scoped rows. Its own cleanup function was invoked; the rerun with the production service pin passed.

An assessment dry-run cleanup command was initially too broad and removed eight older matrix evidence rows. The exact eight rows were restored from the verified predeployment dump through a temporary restore database. Final outbound count returned to the exact predeploy value (**713**). Evidence: `OPERATIONAL-NOTES.txt`.

---

## 9. Rollback and exact redeploy proof

| Step | Result |
| --- | --- |
| Restore previous production app/registry/offer | PASS |
| Classification + held-authority modules absent after rollback | PASS |
| Classification drop-in absent after rollback | PASS |
| Production health after rollback | **200** |
| Unified Candidates master OFF / WATHEFNI override preserved | PASS |
| Additive schema preserved | PASS |
| Global taxonomy preserved (1 release / 43 nodes) | PASS |
| Tenant taxonomy assignments preserved empty | PASS |
| Runs/suggestions/reviews/jobs preserved empty | PASS |
| Redeploy final composite `3c8949…` | PASS |
| Exact file/drop-in hashes match manifest | PASS |
| Production health after redeploy | **200** |
| Requalification after redeploy | **42/42 PASS** |

Evidence:

- `ROLLBACK-BEFORE.txt`
- `ROLLBACK-RESTORED.txt`
- `ROLLBACK-SCHEMA.txt`
- `REDEPLOY.txt`
- `REDEPLOY-FLAGS.txt`
- `REDEPLOY-QUALIFICATION.log`

No schema was dropped.

---

## 10. Final leave-state

```text
production health: 200
service: active + enabled
classification master: OFF
classification tenant allowlist: empty
classification workers: OFF (0 processes / 0 units)
classification UI: OFF
classification manual execution: OFF
classification schema runtime flag: OFF
Unified Candidates master: OFF
Unified Candidates tenants: WATHEFNI only
classification runs/suggestions/reviews/jobs: 0 / 0 / 0 / 0
taxonomy tenant assignments: 0
production dashboard classification markers: 0
staging: unchanged
```

---

## 11. Unresolved risks and canary decision

1. **C0/C1 frozen matrix not fully green** (21/22; isolated interviews entitlement).
2. **Optional-module boundary not fully green** (12/13; incomplete synthetic Job publishability).
3. **Classifier quality risk from staging remains:** weak Technology over-suggestion and `long_unclear` classification need tuning/requalification before a production tenant sees results.
4. **Artifact manifest naming:** `tpc-allowlist2.sha256` is authoritative for `05274349…`; the older `allowlist.sha256` must not be used for promotion.
5. **Production app compatibility is surgical:** future packaging must retain the shared authority replacement for the older Unified Candidates route guards; do not overwrite production with an unreconciled local `app.py`.
6. No real candidate delivery was used to prove live behavior; authorization and existing policy flow were verified with provider mocks, intentionally.

### GO / NO-GO

| Question | Verdict |
| --- | --- |
| Keep exact classification artifact deployed production-dark? | **GO** |
| Keep held communication authority active? | **GO** |
| Enable classification for internal production tenant `WATHEFNI` now? | **NO-GO** |
| Start workers/manual runs/backfill/UI? | **NO-GO** |
| Begin Role Profiles, ranking changes, Person Registry, outreach, or `intake_admit` changes? | **NO-GO** |

Before an internal canary, resolve/requalify the two limited frozen packs, close the classifier quality risks, and execute a separately approved canary plan with explicit monitoring and rollback ownership.

**Stop. Classification remains dark.**
