# Pre-Hiring Unified Candidates — Restored Baseline Requalification

**Date:** 2026-07-25 (UTC)  
**Scope:** Restored-baseline regression requalification only (Candidates C0–C3, Ranking, Reports, Interviews + final sweep + flag rollback)  
**Production:** **Not deployed.** Production `:8010` remained healthy.  
**Feature state left on staging:** `WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=on` with `WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI` only.

---

## Verdict

| Gate | Result |
| --- | --- |
| Restored-baseline production-gating matrices (C0–C3, Ranking, Reports, Interviews) | **GO** — all green after classified harness fixes |
| Held/live authority + flag rollback | **GO** — 14/14 |
| Final frozen sweep | **GO with classified non-blocking gaps** (2 pre-existing harness/env smokes) |
| **Production-dark deployment** | **GO_PRODUCTION_DARK** |

**Production-dark constraints (mandatory):**

1. Deploy only with master flag **OFF** and tenants empty (no production tenant enable).
2. Do not enable classification, Role Profiles, Person Registry, outreach, or Link to Job.
3. Include the C01 staging-matrix harness fix in the ops allowlist (not a product authority change).
4. Pin live staging file hashes from this requal evidence before any promotion.

---

## 1. Baseline identity

| Item | Value |
| --- | --- |
| Source commit | `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2` |
| Contained allowlist artifact SHA | `c0a1fc0d129745999228a657c7acbb602076a42db6ec883a16a4c848bf4bdf45` |
| Staging DB | `wathefni_staging` healthy (`/health` match=true) |
| Feature flag | ON for **`WATHEFNI` only**; other tenants `enabled_for_company=false` (sampled `BOOTMIX01`) |
| Qualification residue | `UCSTG*` / `UCSHOT*` apps, facts, views = **0**; restored `candidates` Kuwait-style phones = **69** |
| Evidence | `/opt/wathefni/staging/staging-evidence/unified-candidates/restored-baseline-requal-20260725T145555Z` |

### Live hashes during this requal

```
236034992d6c92ebc1e1e9800ac4d26d5723bad01e189b84b2ea693d36ca5a0e  app.py
c814d3a65d4ab690d1a57c1867eec4960b3dd208c58f532485eebe15259fa6a3  unified_candidates.py
331047d051ec72b0bd6415b815355877e4aaf5dfaad21b3febe25185642c58e7  unified_candidates_routes.py
```

`unified_candidates.py` is unchanged vs the accepted staging qualification. `app.py` / `unified_candidates_routes.py` differ from the prior qualification evidence record (`9293382c…` / `fc597364…`); late-mount registration is still present in live `app.py`. Recorded as an identity risk below — matrices were executed against the live tree above.

---

## 2. Exact matrix totals

| Matrix | Totals | Result |
| --- | --- | --- |
| Candidates C0/C1 (`candidates-c01-staging-matrix.py`) | **44 / 44** | PASS (after harness fixes) |
| Candidates C2 schema verify | PASS | PASS |
| Candidates C2 staging matrix | **39 / 39** | PASS |
| Candidates C3 schema verify | PASS | PASS |
| Candidates C3 staging matrix | **49 / 49** | PASS |
| Ranking R0–R3 staging | **57 / 57** | PASS |
| Ranking result presentation staging | **213 / 213** | PASS |
| Reports v1 staging | **80 / 80** | PASS |
| Interviews staging | **45 / 45** | PASS |

Held/live separation + tenant flag isolation + rollback proof: **14 / 14 PASS** (`held-authority-rollback.json`).

---

## 3. Failures and classifications

### A. C01 `confirmed_schedule_succeeds` → `module_disabled` (interviews)

| Field | Value |
| --- | --- |
| Classification | **Test harness / restored-baseline mismatch** |
| Evidence | Schedule failed with `required_module: interviews` while C01 seed enabled only `pre_hiring` |
| Product regression? | **No** — interviews staging matrix separately proved green; entitlement fail-closed is expected |
| Fix | C01 seed now enables `pre_hiring` **and** `interviews` |
| Rerun | C01 advanced past interview gates |

### B. C01 `hire_execute_atomic` → missing `companies.country`

| Field | Value |
| --- | --- |
| Classification | **Restored-baseline / harness mismatch** |
| Evidence | `employment_applicability_snapshot_failed` / `Cannot auto-create legal entity without companies.country…` |
| Product regression? | **No** — Kuwait foundation requires country; other staging matrices seed `KW` |
| Fix | C01 company seed sets `country='KW'` |
| Rerun | C01 **44/44 PASS** |

### C. Sweep `smoke-test-jobs-phase1.py`

| Field | Value |
| --- | --- |
| Classification | **Test harness issue** (incomplete publishable job fixture) |
| Evidence | `JobsError: Complete the required job information before publishing` after draft/edit OK |
| Product regression from unified Candidates? | **No** — Jobs phase2 unit pack PASS; Ranking/Reports/Interviews/C0–C3 independent |
| Fix in this requal | **None** (would be unrelated Jobs smoke seed work) |

### D. Sweep `smoke-test-hr2a-mobile-data.py` (36/37)

| Field | Value |
| --- | --- |
| Classification | **Environment / static harness assertion** |
| Evidence | FAIL only: “candidate status updater is explicitly bound to current environment” |
| Product regression from unified Candidates? | **No** — runtime mobile authority packs and tenant isolation PASS |
| Fix in this requal | **None** |

No failure was classified as a real unified Candidates product regression. No Talent Pool authority, lifecycle semantics, or Ranking/Reports/Interviews product code was changed.

---

## 4. Fixes (allowlist)

Changed files in this requal (harness / ops only):

| File | Why |
| --- | --- |
| `wathefni-orchestrator/ops/candidates-c01-staging-matrix.py` | Enable `interviews` module + seed `country='KW'` for fixture companies |
| `ops/run-restored-baseline-matrices.py` | Contained matrix runner |
| `ops/run-restored-baseline-final-sweep.py` | Final sweep runner |
| `ops/restored-baseline-held-rollback-proof.py` | Held gates + flag rollback proof |
| `ops/PREHIRING_UNIFIED_CANDIDATES_RESTORED_BASELINE_REQUALIFICATION.md` | This report |

**Not changed:** unified Candidates product modules, Ranking/Reports/Interviews authorities, production config.

---

## 5. Complete rerun evidence

Host evidence directory:

`/opt/wathefni/staging/staging-evidence/unified-candidates/restored-baseline-requal-20260725T145555Z`

Includes matrix logs, C01 JSON (44/44), held-authority-rollback.json, final-sweep.json, flag-off matrix/lifecycle logs, fixed C01 matrix copy.

### Final sweep (flag ON)

| Pack | Result |
| --- | --- |
| canonical recruiting lifecycle | PASS (78/78 also reconfirmed under flag OFF with full env) |
| Jobs phase2 stage-a unit | PASS |
| Jobs phase1 | FAIL — classified harness (§3C) |
| Offers/Hiring (`smoke-test-offer-lifecycle.py`) | PASS |
| Assessments | PASS |
| Assistant parity | PASS |
| inbound email | PASS |
| bulk import | PASS |
| tiered intake | PASS |
| tenant isolation harness | PASS |
| HR-2A mobile data smoke | 36/37 — classified (§3D) |
| `test_unified_candidates.py` | PASS |
| Dashboard Vitest (local against qualified UI) | **12 files / 54 tests PASS** |
| HR mobile Vitest (local) | **11 files / 44 tests PASS** |

---

## 6. Rollback proof

| Step | Result |
| --- | --- |
| Flag OFF → legacy Candidates list (`unified_candidates` false) | PASS |
| Held row retains `needs_role` + empty job binding | PASS |
| Flag OFF matrices: C01, Ranking R0–R3, Reports, Interviews | **All PASS** |
| Flag OFF canonical lifecycle (full staging env) | **78/78 PASS** |
| Flag ON for `WATHEFNI` restores feature endpoint + Talent Pool visibility | PASS |
| No schema/data rewrite required | PASS |
| Held actions remain denied (shortlist/reject/notify/assessment) | PASS |
| Ranking path does not advisory-score held rows without job context | PASS |

Final flag state restored to **ON / `WATHEFNI` only**.

---

## 7. Zero-residue proof

After proofs and matrix cleanups:

- `UCSTG*` / `UCSHOT*` / `UCREQ*` applications = 0  
- unified fact-review / saved-view qualification markers = 0  
- C01 temporary companies cleaned by matrix teardown (`c01_apps=0`)  
- Restored baseline candidate population retained (`candidates` `965*` = 69)

---

## 8. Unresolved risks

1. **Live `app.py` / routes hash drift** vs prior staging-qualification `deployed.sha256` — pin and reconcile before production-dark packaging.
2. **Jobs phase1 smoke** still incomplete as a publishability fixture (non-blocking for these gates).
3. **HR-2A static env-binding assertion** still fails 1/37 (non-blocking).
4. Production must remain dark for the unified flag; enabling any production tenant is out of scope.
5. Held Talent Pool rows must continue to be excluded from job Ranking, Interviews, Offers, pipeline Reports, and lifecycle mutations — reconfirmed here, must remain fail-closed in any future change.

---

## 9. Stop line

- Restored-baseline requalification of C0–C3 / Ranking / Reports / Interviews: **complete and green**.
- Staging unified feature remains enabled **only for `WATHEFNI`**.
- **Production not deployed.**
- **Production-dark: GO_PRODUCTION_DARK** under the constraints in the Verdict section.
- Classification / Role Profiles / Person Registry / outreach / Link to Job: **not started.**
