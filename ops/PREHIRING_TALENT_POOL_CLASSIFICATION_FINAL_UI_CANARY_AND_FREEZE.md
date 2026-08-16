# Pre-Hiring Talent Pool Classification — Final UI Canary and Freeze

**Date:** 2026-07-26 (UTC+3)  
**Decision:** **NO-GO — PREDEPLOY ARTIFACT ACCEPTANCE FAILED**  
**Production dashboard promoted:** **no**  
**Live production UI canary executed:** **no**  
**Classification leave-state:** **fully OFF for every tenant**  
**Production health:** **200**  
**Persistent classification workers:** **inactive**

## Executive verdict

The exact staging classification dashboard bundle was located and verified byte-for-byte before
production deployment. It contains the previously qualified feature marker, basic filter panel,
optional chip component, and candidate profile section.

It does **not** implement the complete UI contract required by this final canary.

The acceptance audit failed 14 required capabilities:

1. no rendered skill filter;
2. no rendered industry filter;
3. no rendered seniority filter;
4. no rendered experience-band filter;
5. no confidence/state, Needs review, or Unclassified filter;
6. classification filter state is not applied to the Candidates query;
7. classification filter state is not included in saved views;
8. no HR Add control;
9. no HR Correct control;
10. confirm/reject is submitted immediately without explicit UI confirmation;
11. HR review history is not rendered;
12. current/stale state is not rendered;
13. the backend profile response exposes only the latest run, not immutable run history;
14. the Candidates list backend does not project `classification_chip`.

The bundle itself also contains the explicit production-facing text:

> Career area / likely role / skills / seniority filters are reserved for future classification.

Promoting this artifact unchanged could make classification-shaped controls visible, but it could
not pass the requested live filter, row-chip, saved-view, HR-action, or immutable-history gates.
Proceeding would knowingly deploy an incomplete artifact and then require rollback.

The deployment therefore fail-stopped before changing `/var/www/wathefni-dashboard`. No
classification tenant was enabled and no synthetic candidate was created.

## 1. Accepted premise correction

The prior staging qualification used a narrower UI standard:

- marker presence;
- local component rendering;
- High-chip density examples;
- generated payload screenshots;
- 8 component tests.

That report explicitly recorded that:

- the browser click-through was not performed;
- the dashboard was not part of the original staging artifact SHA;
- advanced classification filters were reserved for future work.

The current request requires materially more:

- functional filters over production rows;
- classification-aware saved views;
- Add and Correct actions;
- explicit review confirmation;
- immutable run history;
- current/stale presentation;
- live row-chip projection.

The old staging result is valid for its original marker/presentation scope, but it is not a
qualification of this expanded final UI contract.

## 2. Staging dashboard identity

Source revision recorded by the staging qualification:

`40a4e2621f4818bf7c0f6ce3642032297bfbe7b2`

The classification UI source was modified/untracked relative to that commit. The commit alone is
therefore not a sufficient byte identity. The exact source manifest was also sealed.

| Identity | SHA-256 |
| --- | --- |
| Source manifest | `860352bf28f7a1402c1df5b1671565e8ab0005f1be6eaf2975ed31c6a77b0dfb` |
| Qualified dist manifest | `518382a4b7effd8b4d3719daa1513d08acdc295247bba964f566b62f38226bdc` |
| Canonical qualified asset set | `bdb205f855bb80fccd38adba11d2f5c53adbeed08b8741fafe37837c82d03ee3` |
| Candidate UI composite | `2914540fbe7bda23196fdb985c8f89f5aa62a1cbe4793fcdf2ecc7e08203f296` |
| Main qualified dashboard JavaScript | `688eef6899816c769f1f891215eddc7e4cd427d72a0bab7d2d9b9edac9f03391` |

The seven-file qualified dist manifest verified successfully against
`/opt/wathefni/staging/dashboard-dist`.

The current staging directory tree SHA, including one stale prior JavaScript asset not referenced
by the qualified manifest, is:

`b899f5c5831ea0c86dd198943918e351d546931791210f4b9b04d55e56b6324d`

Only the seven manifest-selected files were treated as the candidate artifact.

## 3. Qualified dist allowlist

| Asset | SHA-256 |
| --- | --- |
| `assets/ConfirmDialog-BUONn0_T.css` | `9f29fa3ea95f534b7c3b2575f0882a9e0625045d26fd2f3dc3c83a6363da85ac` |
| `assets/ConfirmDialog-Dgk27sGZ.js` | `d73a765ea50234d76c9524304069e9e101f166a0bb80076b96a9ea4488642ed6` |
| `assets/dashboard-BH_0JGYz.js` | `688eef6899816c769f1f891215eddc7e4cd427d72a0bab7d2d9b9edac9f03391` |
| `assets/setupConsole-DhxTLcLR.js` | `6abd206d061145288f574244ff1ff37cdc534c8a7971ac566287302b81bf2fc0` |
| `favicon.svg` | `61bc9a161de58248288e6905425d7180f0624c2865007b97d763fdac12043a66` |
| `index.html` | `92136f864a7f4c1405a66c9c4e72b32c485a9f2ba6db36712efa19281969460d` |
| `setup-console.html` | `708d70228151102b30b43af6a93674ef1fc0af5c6ab48afbd3af6f7ce2b5655b` |

All seven hashes matched staging.

## 4. Source allowlist

The sealed source manifest contains:

- `apps/wathefni-dashboard/src/App.tsx`;
- `apps/wathefni-dashboard/src/lib/api.ts`;
- `apps/wathefni-dashboard/src/types.ts`;
- `apps/wathefni-dashboard/src/components/candidates/ClassificationFilters.tsx`;
- `apps/wathefni-dashboard/src/components/candidates/CandidateClassificationSection.tsx`;
- `apps/wathefni-dashboard/src/components/candidates/CandidateGovernedProfile.tsx`;
- `apps/wathefni-dashboard/src/components/candidates/CandidatesTable.tsx`;
- `apps/wathefni-dashboard/src/components/candidates/ClassificationFilters.test.tsx`;
- `apps/wathefni-dashboard/src/components/candidates/CandidatesTable.test.tsx`.

Operational evidence added in this phase:

- `ops/talent-pool-classification-final-ui-preflight.py`
  - SHA-256:
    `97d2561a176471cca44cf3e70a7f56a0a9f174a2787013a2e3d3810580819a45`;
- `ops/evidence/tpc-final-ui-20260725T234953Z/`;
- this report.

No dashboard source or backend product file was changed during this phase.

## 5. Production predeployment state

Before any contemplated dashboard replacement:

| Gate | Result |
| --- | --- |
| Production health | 200 |
| Production dashboard tree SHA | `c7b8b954a48f14c2c3c03d4c7e330772259a4527a53fe6c612524868dbc91e02` |
| Classification master | OFF |
| Classification tenant allowlist | empty |
| Schema runtime | OFF |
| Manual execution | OFF |
| Workers | OFF / inactive |
| Classification UI | OFF |
| Classification runs | 0 |
| Classification suggestions | 0 |
| Classification review events | 0 |
| Classification jobs | 0 |
| Tenant taxonomy nodes | 0 |
| Unified Candidates | master OFF; `WATHEFNI` override unchanged |

The exact v1.2 backend remains deployed dark:

- classifier version: `classifier.deterministic_v1.2`;
- classifier SHA:
  `d97bae99e9d181daaadd384e070951902fa35243d14c92776bd20b712de0505b`.

## 6. Backup and rollback evidence

Although deployment was stopped, the required predeployment backup and rollback package were
completed before the artifact decision.

Backup:

`/opt/wathefni/backups/production-pre-tpc-final-ui-20260725T234953Z`

| Evidence | Result |
| --- | --- |
| Daily production backup | `20260725T234955Z` SUCCESS |
| Contained PostgreSQL dump | verified |
| Dump SHA-256 | `dd2e6dbac97f2a85bb6cdf0c5dbc6d4ba9b9cd747c4f60bc004934593725ecaa` |
| `pg_restore --list` | PASS, 1,130 entries |
| Production dashboard copy | preserved as `dashboard-dist.pre` |
| Classification drop-in | preserved |
| Unified Candidates drop-in | preserved |
| Rollback helper | present and executable |
| Rollback SHA-256 | `e755a374090697d937cb5a42e3c2886b49c369c57ad88dc5971b2714bea57c4f` |

Rollback was not executed because no production dashboard byte was changed.

## 7. Artifact acceptance matrix

### Present in the exact staging artifact

- classification feature endpoint check;
- tenant/UI feature gating;
- classification filter container;
- authority selector;
- Medium opt-in checkbox;
- career-area text input;
- likely-role text input;
- optional compact-chip component;
- candidate profile Classification section;
- current confirmed and AI-suggested lists;
- confirm button;
- reject button;
- evidence preview;
- taxonomy and classifier version badges.

### Missing or non-functional

| Required behavior | Artifact result |
| --- | --- |
| Career area filter returns rows | UI field exists, but filter state is not applied |
| Likely role filter returns rows | UI field exists, but filter state is not applied |
| Skill filter | missing |
| Industry filter | missing |
| Seniority filter | missing |
| Experience-band filter | missing |
| Confidence/state filter | missing |
| Needs review filter | missing |
| Unclassified filter | missing |
| Medium opt-in returns rows | checkbox exists, but filter state is not applied |
| HR-confirmed-only filter | selector exists, but filter state is not applied |
| AI-suggested filter | selector exists, but filter state is not applied |
| Classification saved view | classification state is omitted from save and reload |
| Compact row chip | component exists, but list API never returns `classification_chip` |
| HR Add | missing |
| HR Correct | missing |
| Explicit confirmation | missing; action sends `confirm: true` directly |
| Review history | response field exists but component never renders it |
| Immutable run history | backend response exposes only latest run |
| Current/stale status | absent |

## 8. Why this cannot be corrected by asset promotion alone

Several failures are frontend omissions and would require a newly qualified dashboard build.

Two required behaviors also need additive read-model support:

1. Candidates row chips and server-correct classification filtering require classification
   projection in the paginated Candidates response. The current production query does not join or
   project classification sidecars.
2. Immutable run history/current-stale presentation requires the profile API to return more than
   `ORDER BY created_at DESC LIMIT 1`.

Those are read-only projection changes, not classifier or hiring authority changes, but they are
still backend changes and are outside the user-authorized dashboard-assets-only scope.

Client-side filtering of only the currently loaded page would not be equivalent to correct
production filtering and was not accepted as a workaround.

## 9. Existing component test result

The exact dashboard source’s narrow component packs remain green:

```text
Test Files  2 passed (2)
Tests       8 passed (8)
```

These tests prove basic rendering and existing Unified Candidates presentation. They do not test
server-correct classification filtering, classification-aware saved views, Add/Correct, immutable
run history, or live production behavior.

## 10. Dark promotion result

**Not executed.**

The artifact acceptance failure occurred before production dashboard replacement. Therefore:

- production dashboard SHA stayed
  `c7b8b954a48f14c2c3c03d4c7e330772259a4527a53fe6c612524868dbc91e02`;
- no production static asset changed;
- no application service restart was required for dashboard deployment;
- no classification API execution occurred;
- no classification data was created;
- no Job, lifecycle, ranking, OCR, extraction, embedding, or outbound mutation occurred.

## 11. Live production UI canary

**Not executed.**

No generated HTML or payload-only screenshot was substituted for the requested live browser proof.
There are no new live production screenshots because the candidate artifact was not deployed.

The absence of screenshots is a consequence of the fail-closed predeployment decision, not an
omitted qualification step.

## 12. Tenant isolation, authority, and cleanup

Because the canary never enabled:

- no external tenant was enabled;
- `WATHEFNI` classification was not enabled;
- workers remained OFF;
- no synthetic candidate/application was inserted;
- no classification run, suggestion, review, or queue row was created;
- no saved view or tenant taxonomy node was created;
- no cleanup mutation was required.

The previously accepted backend authority and isolation qualification remains unchanged.

## 13. Regression posture

The accepted production backend qualification immediately preceding this phase remains:

- complete frozen production pack: **26/26 PASS**;
- FAIL: 0;
- LIMITED: 0;
- MISSING: 0;
- Candidates C0/C1: **44/44**;
- optional-module boundary: **301/301**;
- exact protected database baseline restoration: PASS.

A fresh final dark verification was run after the UI preflight:

- **42/42 PASS**;
- health 200;
- all classification flags OFF;
- no tenant enabled;
- sidecars empty;
- no OCR/extraction/embedding mutation;
- held communication authority active;
- Unified Candidates unchanged.

The complete mutation-capable frozen pack was not rerun because the artifact failed before any
production deployment. Running it could not qualify the missing UI behavior and would add
unnecessary synthetic production activity.

## 14. Final feature-flag leave-state

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

Classification is unavailable to every tenant. Unified Candidates remains unchanged for internal
`WATHEFNI`.

## 15. Scope compliance

Not changed or started:

- classifier logic;
- backend authority;
- external tenants;
- persistent workers;
- historical backfill;
- Role Profiles;
- ranking integration;
- Person Registry;
- outreach;
- Job assignment;
- lifecycle integration.

No production dashboard asset was changed.

## 16. Unresolved blockers

A new narrow qualification phase would require:

1. complete dashboard controls and wiring for all requested classification filters;
2. classification-aware saved-view save/reload;
3. Add and Correct controls with explicit confirmation;
4. rendered review history, immutable run history, and current/stale state;
5. additive read-only Candidates projection for chip/filter data;
6. additive read-only profile projection for immutable runs;
7. staging browser qualification of the resulting exact artifact;
8. a newly sealed dist manifest and composite identity.

These requirements cannot be satisfied by promoting the currently qualified staging bytes.

## 17. Final freeze verdict

**NO-GO for dashboard promotion.**

**NO-GO for live `WATHEFNI` UI canary.**

**NO-GO for freezing the complete Talent Pool Classification phase.**

The v1.2 backend remains qualified and safely deployed dark. Production remains healthy and
unchanged.

## 18. Evidence index

- `ops/evidence/tpc-final-ui-20260725T234953Z/PREFLIGHT.json`
- `ops/evidence/tpc-final-ui-20260725T234953Z/source-manifest.sha256`
- `ops/evidence/tpc-final-ui-20260725T234953Z/dashboard-dist.sha256`
- `ops/evidence/tpc-final-ui-20260725T234953Z/final-dark-qualification.json`
- remote evidence:
  `/opt/wathefni/production-evidence/talent-pool-classification-final-ui/20260725T234953Z`
- backup:
  `/opt/wathefni/backups/production-pre-tpc-final-ui-20260725T234953Z`
