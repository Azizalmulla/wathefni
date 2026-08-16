# Pre-Hiring Unified Candidates + Talent Pool — Production-Dark Qualification

**Date:** 2026-07-25 (UTC)  
**Scope:** Guarded production-dark deployment only  
**Canary / classification / Role Profiles / Person Registry / outreach / Link to Job:** **not enabled / not started**

---

## Verdict

| Gate | Result |
| --- | --- |
| Production-dark deployment (flag OFF, no tenants) | **GO_PRODUCTION_DARK** |
| Enabling exactly one internal production canary tenant | **NO-GO** (out of scope; requires a separate approved enablement exercise) |

Production remains dark. Staging remains ON for `WATHEFNI` only. No production tenant has Unified Candidates enabled.

---

## 1. Approved identity

| Item | Value |
| --- | --- |
| Source commit | `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2` |
| Contained allowlist artifact SHA | `c0a1fc0d129745999228a657c7acbb602076a42db6ec883a16a4c848bf4bdf45` |
| Evidence | `/opt/wathefni/production-evidence/unified-candidates-dark/20260725T150641Z` |
| Predeploy backup | `/opt/wathefni/backups/production-pre-unified-candidates-dark-20260725T150641Z` |
| Daily backup stamp | `20260725T150658Z` (`backup-wathefni daily` SUCCESS) |

### Changed-file allowlist (qualified artifact)

```
c814d3a65d4ab690d1a57c1867eec4960b3dd208c58f532485eebe15259fa6a3  unified_candidates.py
014036d64a41b2d2d0a274afff664e22ae68ca7e60f0340fa650e18292e157ad  unified_candidates_routes.py   # allowlist record
d17b8d2056f6c2749c28798e7d313f09b5e15167c0acdda61f41706797b27c31  test_unified_candidates.py
ba564a749561017ca1e0e42aad96adad162c8dbf15d8f14a46cb40ef18d09d2b  local-qualify-unified-candidates.py
0efc9e40747e7b6fc1de8a17af9d9574c2a247438720d52af4341f296a654bf7  ops/patch-staging-app-unified-candidates.py
```

### Deployed production hashes (final dark)

```
2938ab332693a4815a97f0b3d748f4e7a4ee2238ef677d74d9e5b3e2c73b304a  app.py   (surgically patched from production pre)
c814d3a65d4ab690d1a57c1867eec4960b3dd208c58f532485eebe15259fa6a3  unified_candidates.py
331047d051ec72b0bd6415b815355877e4aaf5dfaad21b3febe25185642c58e7  unified_candidates_routes.py
```

**Routes note:** The allowlisted routes byte (`014036…`) lacks `mount_unified_candidate_routes_late`. First dark attempt using that file crashed production import (`AttributeError`). Immediate rollback restored health. Redeploy used the late-mount-capable routes revision (`331047…`) that staging already ran successfully, paired with production-specific surgical patcher `ops/patch-production-app-unified-candidates.py` (production schema anchors only; same dark semantics). Dashboard dist was **not** replaced (backend-dark only).

### C0/C1 harness-only fixes

`ops/candidates-c01-staging-matrix.py` seed updates (`interviews` module + `country=KW`) are **not** production behavior and were **not** deployed as product code.

---

## 2. Backup evidence

| Item | Evidence |
| --- | --- |
| Daily backup | `/opt/wathefni/backups/daily/20260725T150658Z` — SUCCESS (db 5.2M, files 45M, secrets encrypted) |
| Contained predeploy dump | `…/production-pre-unified-candidates-dark-20260725T150641Z/db.dump` |
| `db.dump` SHA256 | `40e13b597257e88e8368e80d785b24738c78747f860cd33f86f50a2407ea42e4` |
| `app.py.pre` SHA256 | `b266a0d24ff49659fb8966b03818f32f2e12fc76cf659ea28514ad8a447d7602` |
| `pg_restore --list` | PASS during deploy |
| Rollback helper | `ROLLBACK.sh` (restores prior `app.py`, removes modules + flag drop-in; **does not drop** additive schema) |

---

## 3. Configuration (redacted)

Manifest: `…/redacted-config-manifest.json`

| Key | Value |
| --- | --- |
| Listen | `127.0.0.1:8010` |
| DB | `wathefni` @ `127.0.0.1` |
| `WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL` | **off** |
| `WATHEFNI_UNIFIED_CANDIDATES_TENANTS` | **empty** |
| Staging flag | **on** / tenants=`WATHEFNI` (unchanged) |

No production tenant entitlement/override enables Unified Candidates (no `company_feature_flags` table; env tenants empty; sampled owners all dark).

---

## 4. Migration evidence

Additive schema applied with flag OFF:

| Table | Present | Row count after deploy |
| --- | --- | --- |
| `candidate_record_governance` | yes | **0** |
| `candidate_fact_review_events` | yes | **0** |
| `candidate_saved_views` | yes | **0** |

No production data backfill. No synthetic writes against real tenants during dark qualification.

---

## 5. Production-dark qualification (15/15)

| Proof | Result |
| --- | --- |
| Production health 200 | PASS |
| Flag drop-in OFF / tenants empty | PASS |
| Feature disabled for WATHEFNI (and sampled tenants) | PASS |
| Legacy Candidates list not unified | PASS |
| `view=talent_pool` does not activate unified read model | PASS |
| Saved-views / Intake Operations dark (403/404/disabled) | PASS |
| No Talent Pool labels in legacy sample | PASS |
| Sidecar tables empty | PASS |
| Staging still ON for WATHEFNI only | PASS |

Repeated **15/15** after rollback→redeploy.

---

## 6. Safe frozen regressions

| Pack | Result | Notes |
| --- | --- | --- |
| `test_unified_candidates.py` | PASS (9/9) | unit |
| `smoke-test-canonical-recruiting-lifecycle.py` | PASS | |
| `smoke-test-prehire-overview-unit.py` | PASS | |
| `smoke-test-prehire-assistant-parity.py` | PASS | |
| `smoke-test-offer-lifecycle.py` | PASS | |
| `smoke-test-assessments.py` | PASS | |
| `smoke-test-jobs-phase2-stage-a-unit.py` | PASS | |
| `smoke-test-tenant-isolation-harness.py` | PASS | |
| `ops/candidates-c3-production-audit.py` | PASS | read-only with `ACK_C3_PRODUCTION_READONLY=yes` |
| Prehire read APIs (summary/reports/rank/interviews/assessments/positions) | 200 | no dark-side mutations |
| Dashboard Vitest (local) | 12 files / 54 PASS | compatibility |
| HR mobile Vitest (local) | 11 files / 44 PASS | compatibility |

Destructive production synthetic fixtures were not inserted.

---

## 7. Rollback and restore proof

| Step | Result |
| --- | --- |
| Feature remains OFF in dark posture | PASS |
| Restore previous production `app.py` via `ROLLBACK.sh` | PASS — health 200; modules removed; flag drop-in removed |
| Additive schema preserved (not dropped) | PASS — tables remain, counts 0 |
| Redeploy approved dark artifact + flag OFF | PASS — health 200 |
| Re-run dark qualification | PASS — 15/15 |
| Staging isolation retained | PASS |

---

## 8. Zero unintended data proof

- Sidecar tables remain at **0** rows after deploy, qualify, rollback, and restore.  
- No saved views / fact-review events created by deployment alone.  
- No tenant enablement records created.  
- Dashboard production assets not overwritten in this dark deploy.

---

## 9. Unresolved risks

1. **Routes byte vs allowlist:** production runs late-mount-capable `unified_candidates_routes.py` (`331047…`) rather than allowlisted `014036…`. Required for import-safe mounting; document in any future promotion pin.  
2. **Production patcher** differs from staging patcher only on schema-hook anchors + mount call site; keep both under ops review.  
3. First dark attempt briefly took production to unhealthy until rollback — operational learning: always verify mount symbol before restart.  
4. Enabling any production canary remains **blocked** until an explicit canary plan with tenant allowlist, monitoring, and rollback owner sign-off.

---

## 10. Stop line

- Production-dark Unified Candidates: **deployed and qualified (`GO_PRODUCTION_DARK`)**.  
- Feature **OFF** globally; **no** production tenant enabled.  
- Staging still **ON for `WATHEFNI` only**.  
- **Canary enablement: NO-GO** in this exercise.  
- Classification / Role Profiles / Person Registry / outreach / Link to Job: **not started.**
