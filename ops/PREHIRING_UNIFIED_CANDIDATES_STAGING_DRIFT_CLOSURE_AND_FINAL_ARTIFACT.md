# Unified Candidates Staging Drift Closure and Final Artifact Seal

**Date:** 2026-07-26  
**Phase:** Narrow Unified Candidates staging qualification closure only  
**Production deploy:** **not performed**  
**Classification enablement / workers / external tenants / Role Profiles:** **not started**

Evidence root:  
`/opt/wathefni/staging/staging-evidence/uc-drift-closure-20260726T002914Z`

---

## 1. Verdict (executive)

| Decision | Result |
| --- | --- |
| Unified Candidates staging drift closure | **GO / PASS** |
| Classification complete-UI non-regression | **GO / PASS (47/47)** |
| Dependent frozen packs | **GO / PASS** (see §7) |
| Zero synthetic residue | **PASS** |
| Combined production-candidate seal | **READY** (identities in §9) |
| Proceed to final production dark promotion + internal `WATHEFNI` UI canary | **GO** (next phase only) |
| Deploy / enable classification / start workers / open external tenants / begin Role Profiles | **NO-GO / not authorized in this phase** |

---

## 2. Blocked gate (precise)

**Gate:** `ops/unified-candidates-staging-qualify.py`  
**Host path (pre-repair):** `/opt/wathefni/staging/orchestrator/ops/unified-candidates-staging-qualify.py`  
**Failure locus:** `seed_fixtures()` — pack never reached view/held/fact/search/rollback assertions while seed aborted.

Observed failure sequence on the diverged staging harness:

1. `ON CONFLICT (company_code, app_key)` invalid against staging/production `applications` PK  
2. Held rows with `position_code=NULL` violating `applications.position_code NOT NULL`  
3. Incomplete `INSERT INTO semantic_documents(...)` omitting NOT NULL columns  
   (`semantic_id`, `content_hash`, `provider`, `model`, `dimensions`)

Authority gates that could not be proven until seed succeeded (and are now proven):  
held job-not-linked, held Talent Pool status, held communication no-outreach, held hide-impersonation, live job retention, no duplicate held, held gates on shortlist/reject/hire/notify/evaluation/assessment, tenant isolation probe, fact append/supersede, search reasons, intake, rollback, zero residue.

---

## 3. Expected vs actual fixture/schema state

### Expected (canonical / production-aligned)

| Object | Expected |
| --- | --- |
| `applications` PK | `PRIMARY KEY (app_key)` only — not `(company_code, app_key)` |
| Held Talent Pool seed | `position_code=''` (non-null unlinked), not `NULL` |
| Search fixture | Prefer candidate **profile text** containing searchable tokens (e.g. Kuwait University) — do **not** require a partial `semantic_documents` insert |
| `semantic_documents` | Full row if used: NOT NULL on `semantic_id`, `content`, `content_hash`, `provider`, `model`, `dimensions`, `metadata` |

### Actual (staging schema — measured)

Schema on staging matches production shape for the contested objects:

- `applications_pkey` = `PRIMARY KEY (app_key)`
- `applications.position_code` = `NOT NULL`
- `semantic_documents` NOT NULL columns as listed in evidence `schema-diagnosis.json` / local `ops/screenshots/uc-drift-closure/uc-drift-diagnose.json`

**Conclusion:** this was **not** a missing additive staging migration and **not** staging-only schema drift vs production.

### Actual (staging harness copy — pre-repair)

| Item | Value |
| --- | --- |
| Diverged harness SHA-256 | `6f006c2053eb02c08f4543deadb59a02b18df70a5016144041fa80548cc3f704` |
| State | Ad-hoc patches from the complete-UI phase (partial ON CONFLICT / empty `position_code` fixes) still attempted incomplete `semantic_documents` INSERT |
| Canonical local harness SHA-256 | `00dc3862b866f2d8a05e1663f1b06e56f2069cbcf19aa6115bb4e8bd1f0c14fd` |

### When / why they diverged

- Canonical local harness already encoded cleanup-before-seed, `position_code=''` for held rows, and profile-text search fixtures (explicit comment: semantic_documents has many NOT NULL cols).
- Staging host retained an older/ad-hoc copy that drifted further during complete-UI qualification troubleshooting (mtime ~2026-07-26 00:25Z), leaving the semantic insert path broken.
- Prior complete-UI report correctly classified UC pack as **fixture/harness-blocked**, not a classification projection defect.

---

## 4. Root-cause classification

| Candidate cause | Evidence |
| --- | --- |
| Stale synthetic seed data alone | Insufficient — seed never completed; residue was not the blocker |
| Missing additive migration | **Ruled out** — staging schema matches production constraints |
| Outdated harness assumptions | **Primary** — staging qualify script disagreed with canonical schema |
| Entitlement/config drift | **Ruled out** as blocker — UC flags ON for `WATHEFNI` after re-enable; pack exercises flag off/on itself |
| Test cleanup residue | **Ruled out** as blocker — zero residue after green run |
| Product regression | **Ruled out** — no runtime product file changed in this repair; held authority gates pass once seed succeeds |

**Label:** outdated / diverged **qualification harness** (with incomplete ad-hoc fixture patches).  
**Not** labeled fixture-only without evidence: the fixture SQL inside the harness was wrong relative to schema; the product authority surface was not regressed.

---

## 5. Exact correction

**Policy applied:** (2) update the qualification harness to the current canonical schema — by syncing the already-correct local `ops/unified-candidates-staging-qualify.py` onto staging.

| Action | Detail |
| --- | --- |
| Backup diverged copy | `$EVIDENCE/harness-pre/unified-candidates-staging-qualify.py.diverged` |
| Deploy canonical harness | SHA `00dc3862b866f2d8a05e1663f1b06e56f2069cbcf19aa6115bb4e8bd1f0c14fd` |
| Product / classification / dashboard code | **unchanged** in this phase |
| Migrations | **none** |
| Authority bypasses | **none** |

Harness corrections (already present in canonical file; now on staging):

- cleanup-before-seed for deterministic reuse  
- held `position_code=''`  
- no incomplete `semantic_documents` insert (profile summary search text instead)  
- no invalid composite `ON CONFLICT (company_code, app_key)`

---

## 6. Proof authority was not weakened

After remediation, Unified Candidates staging pack **50/50 PASS**, including:

- `held_job_not_linked`, `held_status_talent_pool`, `held_comm_no_outreach`, `held_hides_imp`
- `held_gate_shortlist/reject/hire` → 422; `held_gate_notify/evaluation/assessment` → 409  
- `live_keeps_job`, `no_duplicate_held`  
- flag-off company disable + profile 404; tenant allowlist re-enable  
- fact append-only + supersede; rollback preserves fact events / no job binding  
- `zero_residue`

No tenant-isolation weaken, no held/live authority soften, no schema-field bypass, no LIMITED/skip, no staging-only product behavior, no classification behavior change, no Candidates lifecycle semantic change, no Jobs/Ranking/Interviews/Offers/Assessments authority change.

Runtime SHAs unchanged vs complete-UI seal for classification + UC modules (see §9).

---

## 7. Fully green Unified Candidates staging qualification

| Item | Result |
| --- | --- |
| Script | `/opt/wathefni/staging/orchestrator/ops/unified-candidates-staging-qualify.py` |
| Verdict | `GO_STAGING_QUALIFIED` |
| Pass / fail | **50 / 0** |
| LIMITED / MISSING / skipped authority | **none** |
| Evidence | `/opt/wathefni/staging/staging-evidence/unified-candidates/20260726T003000Z` |
| Synthetic cleanup | **exact** — `zero_residue` PASS |

---

## 8. Classification UI non-regression + dependent packs

### Classification complete-UI staging re-qualify

Script: `ops/talent-pool-classification-complete-ui-staging-qualify.py`  
Evidence: `$EVIDENCE/classification-complete-ui-rerequalify/complete-ui-qualification.json`

**47/47 PASS**, covering:

- server-side classification filters (career area, finance, combined AND, OR within dimension, unclassified, high)  
- stable taxonomy node filtering / bilingual catalog  
- pagination under filters  
- chip projection (high only; medium/unclassified suppressed)  
- saved views (create, versioned, deprecated nodes)  
- profile run history + stale current  
- HR confirm / reject / add / correct (preview + confirm-required)  
- feature-OFF hide (taxonomy + chips)  
- cross-tenant disabled  
- workers env OFF; classifier frozen `classifier.deterministic_v1.2`  
- zero residue  

### Dependent regressions

| Pack | Result |
| --- | --- |
| Classification units (`test_talent_pool_classification`) | **18 OK** |
| Held communication authority (`test_candidate_communication_authority`) | **14 OK** |
| Candidates C0/C1 | **44/44 PASS** |
| Optional-module boundary | **301/301 PASS** (`gates=301 failed=0`) |
| Assistant A0–A3 | **79/79 PASS** (`WATHEFNI_EMBEDDING_MODEL=voyage-4-large`) |
| Canonical recruiting lifecycle | **78 passed, 0 failed** |
| Dashboard Vitest | **13 files / 60 tests PASS** |
| Zero-residue audit (UC/TPC synthetic prefixes) | **PASS** (`zero_residue: true`) |

Logs: `$EVIDENCE/frozen-regressions/`.

---

## 9. Sealed production-candidate identities

**No production promote performed.** Seal only.

| Item | Value |
| --- | --- |
| Source revision | `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2` |
| Classifier | `classifier.deterministic_v1.2` |
| Orchestrator manifest SHA-256 | `bf5674acae8c47932185810a919142936fa10f14af6467f41b79c505ff7caca5` |
| Dashboard manifest SHA-256 | `ea282fce7c6c571843b1ff0691b4f09e677922af421a439642c3a499a9b1473f` |
| Dashboard asset-tree SHA-256 | `ea282fce7c6c571843b1ff0691b4f09e677922af421a439642c3a499a9b1473f` |
| Dashboard main JS | `dashboard-C0lgzkSg.js` / `997e5c18f70f346cc800bf3ac53b0ac59fefe346c46fc1f72de878fb2252d50f` |
| **Final combined candidate SHA-256** | `4e156bcc736299fe9cfdd57c8e1fc7799b525fcf7cc50299c2baaebc1eb67089` |

### Runtime changed-file allowlist (promote-eligible)

| File | SHA-256 |
| --- | --- |
| `talent_pool_classification.py` | `4e091456d98f69b3dbf1537051d7de814db60238f22dd24ab97a4524665f3a30` |
| `talent_pool_classification_routes.py` | `882bfb0e9088b46bc5dca1224c3fd4640d8fd987b88f3ed1fffb0edecb4e60c6` |
| `talent_pool_taxonomy_v1.json` | `320d0a1f5eb19413f66337f81df955eadfe0e843d190b6048af313669c10fbb1` |
| `unified_candidates.py` | `945feb810285e1ae14e78f68432cf7c64d00b506519b442fbbcd11f23f165421` |
| `candidate_communication_authority.py` | `8a3949eac6d72c7f18514810171298615e1fded40e81afba2ee91239305aab53` |

Plus prior complete-UI surgical staging `app.py` patch markers  
(`TALENT_POOL_CLASSIFICATION_COMPLETE_UI_PATCH`) and dashboard dist above — unchanged this phase.

### Test-only changed-file allowlist (exclude from runtime promotion)

| File | SHA-256 |
| --- | --- |
| `ops/unified-candidates-staging-qualify.py` | `00dc3862b866f2d8a05e1663f1b06e56f2069cbcf19aa6115bb4e8bd1f0c14fd` |

Diverged pre-repair harness (archived, not for promote):  
`6f006c2053eb02c08f4543deadb59a02b18df70a5016144041fa80548cc3f704`

Seal JSON: `$EVIDENCE/seal/combined-candidate.json`  
Local mirror: `ops/screenshots/uc-drift-closure/seal/`

---

## 10. Leave-state (unchanged intent; verified)

**Staging**

- Unified Candidates: master **ON**, tenants=`WATHEFNI`  
- Classification: master **OFF**; tenants=`WATHEFNI`; schema **ON**; manual **ON**; UI **ON**; workers **OFF**  
- Dashboard only at `/opt/wathefni/staging/dashboard-dist` (not `/var/www`)

**Production**

- Classification **fully OFF** (schema/manual/UI/workers/tenants empty/off)  
- No dashboard promote in this phase  
- No production data or configuration changes for this closure

---

## 11. GO / NO-GO

| Decision | Verdict |
| --- | --- |
| UC staging drift closure complete | **GO** |
| Combined candidate sealed for next phase | **GO** |
| Final production dark promotion + internal `WATHEFNI` UI canary | **GO** (authorized as next phase; **not executed here**) |
| Deploy now / enable classification / start workers / enable external tenants / begin Role Profiles | **NO-GO** |

**Stop after this report.**
