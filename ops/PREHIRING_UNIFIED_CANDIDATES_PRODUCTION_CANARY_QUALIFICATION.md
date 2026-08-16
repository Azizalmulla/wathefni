# Pre-Hiring Unified Candidates + Talent Pool — Production Canary Qualification

**Date:** 2026-07-25 (UTC)  
**Scope:** Guarded **internal production canary** for tenant `WATHEFNI` only  
**Global master flag:** **OFF** (`WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=off`)  
**Tenant override:** `WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI`  
**External / client tenants:** **not enabled**  
**Classification / Role Profiles / Person Registry / outreach / Link to Job / `intake_admit`:** **not implemented / not enabled**

---

## Verdict

| Gate | Result |
| --- | --- |
| Production canary for internal `WATHEFNI` (tenant override only) | **GO_PRODUCTION_CANARY** |
| Global production release / master ON / all tenants | **NO-GO** |
| Enable any external or real client tenant | **NO-GO** |
| Begin classification / Role Profiles / Person Registry | **NO-GO** |

Automated canary matrix: **66/66 PASS** (`GO_PRODUCTION_CANARY`).  
Canary remains **enabled for `WATHEFNI` only** with master **OFF**. Synthetic fixtures cleaned to **zero residue**.

---

## 1. Approved identity and deployed bytes

| Item | Value |
| --- | --- |
| Source commit | `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2` |
| Contained allowlist artifact SHA | `c0a1fc0d129745999228a657c7acbb602076a42db6ec883a16a4c848bf4bdf45` |
| Evidence | `/opt/wathefni/production-evidence/unified-candidates-canary/20260725T200746Z` |
| Prior dark backup / rollback | `/opt/wathefni/backups/production-pre-unified-candidates-dark-20260725T150641Z/ROLLBACK.sh` |
| Production health | **200** before, during, and after |

### Production hashes at canary qualify

```
2938ab332693a4815a97f0b3d748f4e7a4ee2238ef677d74d9e5b3e2c73b304a  app.py
6d7fa436ae05f345047896b7ee0d94f941117c062464ba9e9b7e8e612da5ae27  unified_candidates.py   # canary semantics: TENANTS alone enables listed companies
331047d051ec72b0bd6415b815355877e4aaf5dfaad21b3febe25185642c58e7  unified_candidates_routes.py  # late-mount capable
```

**Canary semantics note:** `feature_enabled_for_company` enables only companies listed in `WATHEFNI_UNIFIED_CANDIDATES_TENANTS`. An empty tenant list disables everyone. Master alone never enables all tenants. With master OFF + `TENANTS=WATHEFNI`, `activation_mode=tenant_canary_override`.

**Dashboard UI (contained):** production static dashboard was promoted from the already-qualified staging dist so the feature-gated Unified Candidates UI can render for canary. Non-canary tenants remain feature-disabled via API (`enabled_for_company=false`). Pre-promote assets retained under evidence `dashboard-backup/`.

Staging isolation unchanged: master **on**, tenants=`WATHEFNI`.

---

## 2. Pre-canary confirmation

From `PRECANARY.txt`:

| Check | Result |
| --- | --- |
| Production health 200 | PASS |
| Global master OFF | PASS |
| Tenant override empty before enable | PASS (reset from prior partial canary, then re-proven empty) |
| Feature disabled for WATHEFNI before enable | PASS |
| Sidecar tables empty | PASS (`governance=0`, `facts=0`, `views=0`) |
| Previous dark artifact + `ROLLBACK.sh` available | PASS |
| Late-mount routes present (`331047…`) | PASS |
| Staging unchanged | PASS |

---

## 3. Tenant override proof

| Step | Proof |
| --- | --- |
| Enable `TENANTS=WATHEFNI` only; master stays `off` | systemd drop-in + feature API `activation_mode=tenant_canary_override` |
| WATHEFNI sees unified list | `unified_candidates=true`; views All / Active / Talent Pool / Hired / Archived / Restricted PASS |
| Global flag unmodified | `TALENT_POOL=off` throughout |
| No unrelated workers / outbound started | no worker enablement; delivery packs dry-run / unit only |

Final production drop-in (left in place after qualify):

```
Environment=WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=off
Environment=WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI
```

---

## 4. Before / after screenshots

Local index: `ops/screenshots/unified-candidates-production-canary/INDEX.md`

| State | Evidence |
| --- | --- |
| **Before** (override OFF) | `ops/screenshots/unified-candidates-production-canary/before/before-legacy-candidates.png` — separate Intake Review; banner that held intake stays out of the live list until Unified Candidates is enabled; no Talent Pool / Intake Operations nav |
| **After** unified table | `…/after/after-unified-candidates-table.png` — held + live in one Candidates table; Job `Not linked`; Status `Talent Pool`; Intake Operations in nav; large Intake Review list absent |
| **After** filters | `…/after/after-unified-candidates-filters.png` — All / Active applications / Talent Pool / Hired / Archived / Restricted |
| **After** held profile | `…/after/after-held-governed-profile.png` — sender provenance separate; missing facts as incomplete / not extracted; append-only HR fact review note; live applications section separate |
| **After** Intake Operations | `…/after/after-intake-operations.png` — queued / processing / incomplete / failed / unsupported / password-protected / quarantined (release forbidden) / ready held |

---

## 5. Unified table and filter qualification

Synthetic fixtures (marker `unified_candidates_prod_canary_v1`, prefix `UCCY…`) covered:

- active Job application  
- held `needs_role`  
- held `import_review`  
- hired  
- archived held  
- restricted  
- failed intake  
- multi-CV file versions  
- missing / unknown facts  
- append-only HR fact correction  
- semantic-search text fixture  

| Proof | Result |
| --- | --- |
| Held + live in same Candidates table | PASS |
| Held: Job `Not linked`, Status Talent Pool, entry method, CV state, assessment N/A, communication no outreach | PASS |
| Live application behavior unchanged | PASS (`live_keeps_job`) |
| No duplicate held in old Intake Review list | PASS (unified path; large Intake Review absent in after UI) |
| Attention surface → Intake Operations | PASS (`intake_attention`) |
| Views: All / Active / Talent Pool / Hired / Archived / Restricted | PASS |
| Saved views create / list / delete | PASS |
| Search reasons + restricted excluded from normal search | PASS |

---

## 6. Held-action gate proof

UI: held profile shows no recruiting lifecycle / Ranking / Interviews / Offers / outreach actions (governed profile panel).

Direct API attempts against held `needs_role` (all fail-closed):

| Gate | HTTP | Result |
| --- | --- | --- |
| shortlist / reject / hire / notify / evaluation / assessment | 403/404/409/422 | PASS |
| interviews / offers / lifecycle | 403/404/409/422 | PASS |
| link-to-job / intake-admit / AI assign-job | **405** (route absent) | PASS fail-closed |
| Ranking payload excludes held canary key | PASS |
| Profile `link_to_job.enabled=false` | PASS |

Backend does not admit held records into Ranking / lifecycle / outreach paths.

---

## 7. Fact and search proof

| Proof | Result |
| --- | --- |
| Sender provenance separate from CV-grounded contacts | PASS |
| Synthetic `imp-…` hidden from normal HR phone display | PASS (`held_hides_imp`) |
| Documents / multi-CV versions seeded & cleaned via `file_registry` | PASS |
| Missing facts not phrased as negative facts | PASS |
| Fact review append-only (≥2 events during canary) | PASS |
| Search returns match reasons; restricted excluded | PASS |

---

## 8. Intake Operations

| Bucket | Visibility |
| --- | --- |
| queued / processing / incomplete / failed / unsupported / password-protected / quarantined / ready held | Surface present; counts API-backed |
| Quarantined / malware | Card shows **Release forbidden**; general HR cannot release/download |

---

## 9. Cross-tenant isolation

Production `companies` currently contains **only** `WATHEFNI` (no external client tenant rows).

Proof method: ephemeral synthetic company `UCCX…` + owner session, then deleted.

| Check | Result |
| --- | --- |
| Feature / applications / intake for probe company | **403** dark (`cross_tenant_dark` PASS) |
| No probe company left after cleanup | PASS (`companies=WATHEFNI` only) |
| No sidecar rows for other tenants | PASS (sidecar totals 0) |

---

## 10. Frozen production regressions

| Pack | Result |
| --- | --- |
| `test_unified_candidates.py` | PASS |
| `smoke-test-canonical-recruiting-lifecycle.py` | PASS |
| `smoke-test-offer-lifecycle.py` | PASS |
| `smoke-test-assessments.py` | PASS |
| `smoke-test-prehire-assistant-parity.py` | PASS |
| `smoke-test-tenant-isolation-harness.py` | PASS |
| `smoke-test-jobs-phase2-stage-a-unit.py` | PASS |
| `smoke-test-inbound-email.py` | PASS |
| `smoke-test-bulk-cv-import.py` | PASS |
| `smoke-test-dashboard-auth.py` | SKIP / env — expects repo `App.tsx` path on host (not a product regression) |
| `smoke-test-hr2a-mobile-data.py` | 36 PASS / 1 FAIL — `candidate status updater bound to current environment` (pre-existing / env binding; not introduced by canary enablement) |

Candidates C0–C3, Jobs, Ranking, Reports, Interviews, Offers, Assessments, Assistant, and canonical lifecycle authorities were not rewritten; canary only toggles the unified read surface for `WATHEFNI`.

---

## 11. Rollback proof

| Step | Result |
| --- | --- |
| Clear `TENANTS=` (master stays OFF) | PASS — feature disabled for WATHEFNI |
| Legacy Candidates experience returns | PASS (`unified_candidates` false) |
| Synthetic sidecar data preserved while inactive | PASS (fact event counts unchanged across rollback) |
| No Job-binding mutation on held row | PASS (`needs_role`, empty position) |
| Re-enable `TENANTS=WATHEFNI` | PASS — unified Talent Pool restored without migration / rewrite |
| Health remains 200 | PASS |

Full code rollback (modules + prior `app.py`) remains available via dark `ROLLBACK.sh` if needed; **not** executed after successful canary (would remove canary capability).

---

## 12. Zero-residue proof

| Check | Result |
| --- | --- |
| Canary applications / candidates / governance / facts / saved views deleted | PASS |
| Sidecar tables return to **0** | PASS |
| No `UCCX` probe company remains | PASS |
| Only company in production DB | `WATHEFNI` |
| No lifecycle / Job-binding mutation retained for fixtures | PASS |

---

## 13. Unresolved risks

1. **Single real production company:** isolation vs other *real* client tenants is N/A until additional companies exist; proved via ephemeral synthetic company.  
2. **Canary module hash** `6d7fa436…` differs from dark `c814d3a…` only for tenant-override-with-master-OFF semantics — pin in future release notes.  
3. **Routes pin** remains late-mount `331047…` (not allowlist `014036…`) — required for safe mount.  
4. **Dashboard promote** is feature-gated but broadens static UI surface for all sessions; non-canary companies still receive `enabled_for_company=false`. Keep pre-promote backup until global release decision.  
5. **Link-to-Job / `intake_admit`** fail with **405** (absent routes) rather than a dedicated business error — still fail-closed; do not implement these in canary.  
6. Enabling canary surfaces existing real held intake into the unified table for `WATHEFNI` (expected); continue not to run outreach or Link to Job.  
7. HR-2A mobile smoke still has one environment-binding failure independent of this canary.

---

## 14. Stop line

- **GO** to leave the **WATHEFNI-only** production canary enabled (master OFF).  
- **NO-GO** for global production release, master ON, or any external tenant.  
- **Do not** start classification, Role Profiles, Person Registry, outreach, Link to Job, or `intake_admit`.  
- Staging remains isolated and unchanged.  
- Report complete; stop.
