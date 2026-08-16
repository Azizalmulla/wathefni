# Pre-Hiring Talent Pool Classification — Staging Qualification

**Status:** Contained **staging deploy + qualification complete**  
**Date:** 2026-07-25  
**Production deploy:** **not performed**  
**External tenants:** **not enabled**  
**Background classification workers:** **OFF**  
**Role Profiles / ranking / Person Registry / outreach / Job assignment / lifecycle mutation:** **not implemented**

---

## Verdict

| Gate | Result |
| --- | --- |
| Contained staging classification (WATHEFNI only) | **GO_STAGING** (82/82) |
| Production-dark deployment (master OFF, workers OFF, no external tenants) | **GO** for orchestrator + taxonomy artifact |
| Production enable / external tenants / workers | **NO-GO** |
| Role Profiles / ranking / Job assignment / outreach | **NO-GO** |

**Stop condition met.** No production deploy. No external tenants. No Role Profiles.

---

## Artifact identity

| Field | Value |
| --- | --- |
| Source commit | `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2` |
| Allowlist artifact SHA | `052743494cbc47efed07e999913e8b8ddbf509124ea3f17efac76c467a3fa973` |
| Taxonomy version | `taxonomy_v1.1.0` |
| Classifier version | `classifier.deterministic_v1.1` |
| Evidence root | `/opt/wathefni/staging/staging-evidence/talent-pool-classification/20260725T203327Z` |
| Qualify run | `qualify-r3` → `GO_STAGING` |
| Dashboard dist SHA (staging) | see `ops/screenshots/talent-pool-classification-staging/dashboard-dist.sha256` |

### Changed-file allowlist (orchestrator)

- `talent_pool_classification.py`
- `talent_pool_classification_routes.py`
- `talent_pool_taxonomy_v1.json`
- `test_talent_pool_classification.py`
- `local-qualify-talent-pool-classification.py`
- `ops/patch-staging-app-talent-pool-classification.py`

### Staging app.py surgical patch

- Late mount of Unified Candidates + classification **before SPA catch-all** (repairs latent mid-file UC mount that crashed staging on restart).
- Classification routes independent of Unified Candidates flags.

### Staging dashboard (contained)

- Built from local `apps/wathefni-dashboard` with Classification filters / compact chip / profile section.
- Deployed only to `/opt/wathefni/staging/dashboard-dist`.
- Backup: `/opt/wathefni/backups/staging-pre-talent-pool-classification-20260725T203327Z/dashboard-dist/`.

Production orchestrator **does not** contain `talent_pool_classification.py` (asserted).

---

## Staging backup and migration proof

| Item | Path / proof |
| --- | --- |
| Backup root | `/opt/wathefni/backups/staging-pre-talent-pool-classification-20260725T203327Z` |
| DB dump SHA | `16604dcb3fb6ae47c75cd1a8f68a56623b7b7a3ee5e2ae684d6b19753fd3546e` |
| `app.py.pre` SHA | `f8c59f17deea7bf2732e650ff288bb55db5010bd203c79f48b06be0468c6c996` |
| Rollback helper | `…/ROLLBACK.sh` |
| Schema | Additive `ensure_classification_schema` + `seed_global_taxonomy` → **43** nodes, `taxonomy_v1.1.0` |
| Redacted config | `…/redacted-config-manifest.txt` and `ops/screenshots/talent-pool-classification-staging/redacted-config-manifest.txt` |

No destructive rewrite of HR-confirmed facts or lifecycle tables. Classification tables are additive.

---

## Feature flags (final staging state)

Independent of Unified Candidates:

```
WATHEFNI_TALENT_POOL_CLASSIFICATION=off          # master OFF
WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS=WATHEFNI
WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA=on
WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL=on
WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off  # persistent workers never enabled
WATHEFNI_TALENT_POOL_CLASSIFICATION_UI=on
```

Unified Candidates (unchanged, independent drop-in):

```
WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=on
WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI
```

Qualification proved: dark → enable WATHEFNI → rollback OFF → re-enable WATHEFNI. Cross-tenant probe remained dark.

---

## Graduated outcomes (staging synthetic)

Evidence: `qualify-r3/outcomes.json`.

| Fixture | Status | Outcome language | Notes |
| --- | --- | --- | --- |
| `software` | `classified` | Clear evidence | Technology + Software Engineer; High+Medium; skills/certs/industry |
| `multi` | `classified_multi` | Multiple relevant areas | Technology, Engineering, Operations — **not forced to one** |
| `career_change` | `classified_multi` | Multiple relevant areas | Mechanical + Software / Python preserved |
| `short_clear` | `classified_multi` | Multiple relevant areas | Junior/intern + Technology — **short CV not penalized** |
| `incomplete_facts` | `classified` | Clear evidence | Raw text supplied Python/SQL/Technology despite empty skills facts |
| `insufficient` | `unclassified` | Insufficient evidence to classify | No active suggestions |
| `arabic` / `english` / `bilingual` | multi/clear | EN/AR evidence paths | Labels resolve via bilingual taxonomy |
| `hr` / `finance` / `engineering` / `sales` / `marketing` / `operations` | clear or multi | Sensible primary functions | Every suggestion carried evidence |
| `long_unclear` | `classified` | Clear evidence | Soft classifier found weak Technology cue — see risks |

UI confidence bands observed: **High** / **Medium** only (no fake percentages). Medium remains usable and advisory.

**Needs review:** Covered by unit pack `test_talent_pool_classification.py` (staging pack PASS). Staging synthetic corpus emphasized clear / multi / unclassified; conflicting-needs-review remains unit-proven rather than fixture-dominant on staging.

Judgmental wording (**weak/bad/poor CV**) was not used in outcomes or profile copy.

---

## Evidence and confidence proof

- Every active suggestion in one-shot runs required non-empty `evidence[]` (`evidence_*` checks PASS).
- High-only compact chip policy reflected in UX density HTML/PNG.
- Medium suggestions present on several fixtures without auto-unclassify.
- OCR never triggered (`oneshot_*_no_ocr`, `http_run_no_ocr_no_workers`).
- Manual HTTP run loads **normalized CV text** from `raw_json` (not OCR; not facts-only).

---

## Immutable runs and HR events

- Idempotent reclassify for identical versions: `reclassify_idempotent` PASS.
- HR confirm + reject append-only; reclassify does not wipe events: `hr_confirm_survives`, `hr_events_not_overwritten_by_run` PASS.
- Queue jobs recorded and completed as `completed_manual` with **workers OFF**: `bounded_queue_jobs_present`, `workers_never_enabled` PASS.
- No unrestricted historical backfill.

---

## Authority-gate proof

Classification cannot assign Jobs / mutate lifecycle:

| Check | Result |
| --- | --- |
| shortlist / hire / intake-admit on held synthetic | blocked (4xx) |
| `position_code` / status remain `needs_role` + empty | PASS |
| Classification run `lifecycle_mutated=false`, `workers_started=false` | PASS |
| Classification has no notify route; run payload has no message side effect | PASS |
| Production module absent | PASS |

**Known independent gap (not classification):** staging `POST …/notify` for `needs_role` is not yet fail-closed (dry-run email succeeded). Documented as `gate_notify_held_gap_documented`. Classification did not invoke notify. Evaluation ranking remains blocked for held statuses.

---

## Cross-channel parity

Classifier authority is canonical stored text + facts versions (email / WhatsApp / upload / import differ only in provenance). Staging fixtures used `intake.source=email` and a second software application version key; same classifier/taxonomy versions apply after extraction. Full multi-ingress live matrix was not re-run; architectural convergence is unchanged from Unified Candidates canary.

---

## UX density screenshots

| Asset | Path |
| --- | --- |
| Table density (High chip vs hidden) | `ops/screenshots/talent-pool-classification-staging/candidates-table-density.png` |
| Filters panel | `ops/screenshots/talent-pool-classification-staging/classification-filters.png` |
| Local profile / chip references | `…/classification-profile.png`, `…/candidates-table-with-chip.png` |
| HTML sources | `…/ux/*.html` |

Principles preserved: clean table, no permanent classification columns, at most one High chip, Medium/Needs review/Unclassified in profile + filters.

Staging dashboard dist now includes `classification/feature`, `classification-filter-bar`, `classification-compact-chip`, `candidate-classification-section`.

---

## Frozen regressions (staging packs)

All PASS under staging DB binding:

- `test_talent_pool_classification.py`
- `test_unified_candidates.py`
- `smoke-test-canonical-recruiting-lifecycle.py`
- `smoke-test-tenant-isolation-harness.py`
- `smoke-test-jobs-phase2-stage-a-unit.py`
- `smoke-test-offer-lifecycle.py`
- `smoke-test-assessments.py`
- `smoke-test-prehire-assistant-parity.py`

Local pre-deploy: units 14/14, local qualify 60/60 GO_LOCAL.

---

## Rollback proof

1. Tenant/UI flags OFF → feature `enabled_for_company=false` (`rollback_disables`).
2. Suggestion + review history preserved (`rollback_preserves_history`).
3. Unified Candidates drop-in untouched; staging health OK after late-mount repair.
4. Re-enable `TENANTS=WATHEFNI` restores classification (`reenable`).
5. No migration rewrite required to disable; `ROLLBACK.sh` restores pre-patch `app.py` and removes classification modules if a full code rollback is needed.

---

## Zero-residue proof

Synthetic prefix cleanup removed applications, runs, suggestions, reviews, jobs, tenant TPC nodes. Final counts for prefix: **0** (`zero_residue` PASS).

Taxonomy global seed remains (expected product data, not synthetic residue).

---

## Unresolved risks

1. **Held notify fail-closed gap on staging** — `needs_role` notify still succeeds via registry dry-run; unrelated to classification artifact; should be closed before broader Talent Pool outreach claims.
2. **Soft Technology bias** — some non-tech fixtures also received `fn.technology` Medium/High alongside the intended function (graduated multi-label). Operationally useful but may over-suggest Technology; tune aliases/weights before production enable.
3. **`long_unclear` not Needs review** — generic wording still mapped Clear Technology; conflicting/Needs review remains stronger in unit tests than this staging fixture.
4. **Dashboard was not in the original orchestrator allowlist SHA** — staging UI dist deployed afterward; include dashboard hash in any production-dark package list.
5. **Live browser canary on staging UI** — density screenshots are generated from staging outcomes + built components; operator click-through on staging URL was not separately recorded.

---

## Production-dark GO/NO-GO

**GO for production-dark packaging** of the classification orchestrator artifact **only if**:

- master remains **OFF**
- workers remain **OFF**
- tenants allowlist **empty** (or no external tenants)
- UI **OFF** by default
- production binary deploy is a later, separately gated exercise

**NO-GO** for:

- enabling any non-`WATHEFNI` tenant
- turning workers ON
- production enablement / backfill
- Role Profiles, ranking, Person Registry, outreach, Job assignment, lifecycle authority

---

## Final staging leave-state

- Classification: master OFF, workers OFF, **TENANTS=WATHEFNI**, UI/manual ON, schema ON  
- Unified Candidates: ON for WATHEFNI (independent)  
- Production: classification module **absent**  
- Synthetic fixtures: **cleaned**
