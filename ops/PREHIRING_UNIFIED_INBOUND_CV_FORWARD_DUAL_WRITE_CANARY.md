# Pre-hiring Unified Inbound CV — Forward Dual-Write Canary Qualification

Date: 2026-07-27 (Asia/Kuwait) / deploy stamp `20260727T004930Z`  
Internal canary stamp: `20260727T004937Z`  
Prerequisites accepted: production-dark `20260727T002415Z`; legacy binding audit `20260727T003453Z`; legacy backfill `20260727T004230Z`  
Host: `root@76.13.63.68`  
Database: `wathefni` (production only)  
Tenant: **WATHEFNI** only  
Orchestrator: `/opt/wathefni/orchestrator` (`127.0.0.1:8010`)

Evidence:
- Remote: `/opt/wathefni/production-evidence/unified-inbound-cv-forward-dual-write-canary/20260727T004930Z/`
- Local: `ops/screenshots/unified-inbound-cv-forward-dual-write-canary/20260727T004930Z/`
- Script: `ops/unified-inbound-cv-forward-dual-write-canary.py`
- Deploy: `ops/deploy-unified-inbound-cv-forward-dual-write-canary.sh`

Scope: **controlled forward dual-write canary** through unified dual-write / Wave 4 authorities while live email, WhatsApp, and manual paths remain authoritative.  
Enforcement: **OFF** (`WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE` absent)  
Channel cutover: **not performed**

Canary Job: `J2P2_PROD_TEST` / `APPLY-WATHEFNI-J2P2_PROD_TEST`  
Canary phones: `96555570001`…`96555570004` (distinct from legacy smoke `9655555013x`)  
Job applications tagged: `data_source=smoke_test`, `data_source_detail=forward_dual_write_canary:20260727T004937Z:quarantined`

---

## Verdict

| Gate | Result |
|---|---|
| 5 owner-authorized canary cases | **PASS** (71/71 checks) |
| One intake event/item/document per case | **PASS** |
| Clean scan + correct extraction plan (local-first PDF) | **PASS** |
| One person/subject decision per contact case | **PASS** |
| Talent Pool entry when no Job | **PASS** (non-actionable) |
| Reusable `cv_version` | **PASS** |
| CK person/subject index meta + app: compat | **PASS** |
| No duplicate person/application for canary contacts | **PASS** |
| Exact `application_job_binding` for Job flows | **PASS** (2) |
| `application_cv_binding` pins chosen CV | **PASS** (2) |
| Held imports remain unbound / shadow-deny | **PASS** (2) |
| Legacy smoke apps remain shadow-deny | **PASS** (5) |
| Unrelated apps/candidates unchanged | **PASS** (18→18 / 21→21) |
| Health 200 pre/post | **PASS** |
| ENFORCE OFF; channels authoritative | **PASS** |

### Explicit GO / NO-GO

| Decision | Result |
|---|---|
| Forward dual-write canary qualification (this task) | **GO / PASS** |
| Keep production-dark + shadow + legacy backfill | **GO** |
| Controlled **channel cutover** (email / WhatsApp / manual → envelope authority) | **NO-GO** |
| Enabling `WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE` | **NO-GO** |
| External tenants / Role Profiles | **NO-GO** |

**Why cutover remains NO-GO:** this canary proves forward dual-write correctness via in-process dual-write / adapter / promote authorities on a quarantined WATHEFNI set. Live webhook/dashboard handlers were **not** switched; ENFORCE stays **OFF**; cutover still needs separate owner authorization and live-path observation under that authorization.

---

## Canary set

| # | Case | Contact / app | Job? |
|---|---|---|---|
| 1 | Inbound email CV | phone `96555570001` | no |
| 2 | Unsolicited WhatsApp CV | phone `96555570002` | no |
| 3 | Manual dashboard CV upload | batch `forward_dual_write_canary-batch-…` (held) | no |
| 4 | WhatsApp apply-code → exact Job | `96555570003-WATHEFNI-J2P2_PROD_TEST` | yes (`J2P2_PROD_TEST`) |
| 5 | Talent Pool → later exact Job promote | `96555570004-WATHEFNI-J2P2_PROD_TEST` | yes (`J2P2_PROD_TEST`) |

---

## Per-case proof

### 1) Email CV, no Job

| Check | Evidence |
|---|---|
| One source event (idempotent replay) | Same `event_id` on dual write + replay |
| One item / one document | `item_ids` length 1; document linked |
| Scan / extraction path | Shared stages: document_acceptance, mime_content_validation, local_extraction **completed**; `local_first=true` |
| Person/subject | `linked` person `98e2ebdc-fede-5c42-a11a-9c6194ec1dea` |
| Talent Pool | entry `ecc759c8-839c-5f69-8980-fbc8a9e75a07`, **actionable=false** |
| `cv_version` | `e25d237f-5e45-550d-8c7d-92c0b0c3eabf` (reuse returns same id; 1 row) |
| CK indexing | person/subject index meta searchable + non-actionable; app: compat OK |
| No Job application invented | `creates_job_application=false` |

### 2) Unsolicited WhatsApp CV, no Job

| Check | Evidence |
|---|---|
| Adapter | `adapt_whatsapp_unsolicited` OK; does not create Job app |
| One item | receipt `item_ids` length 1 |
| Scan / extraction | shared stages `local_first=true` |
| Person | `ff8a7fdc-108e-51ca-bd4d-b2c2cab1df0a` |
| Talent Pool | `cdea32d2-cd31-5e33-94a9-32b51a31bbb4`, non-actionable |
| `cv_version` | `ba2f088b-a2e2-5c3f-ad0f-0f0ecc52cb51` |
| HR visibility | unsolicited held / non-actionable |

### 3) Manual dashboard CV upload, no Job

| Check | Evidence |
|---|---|
| Adapter | `adapt_manual_import` OK; `held_by_default=true`; no Job invent |
| One item | receipt `item_ids` length 1 |
| Scan / extraction | shared stages `local_first=true` |
| Person/subject | subject present; person may be review/skip without phone (held import posture) |
| Talent Pool | `e7c8f259-cdb1-5779-aa2a-89e160f99808`, **actionable=false** |
| `cv_version` | `ed869bf6-60c7-5093-9c33-0491f7364902` |

### 4) WhatsApp apply-code → exact Job

Authoritative wrapper simulated as Stage B would: quarantined `smoke_test` application on `J2P2_PROD_TEST`, then dual-write adapter + `promote_with_verified_job_binding`.

| Check | Evidence |
|---|---|
| App | `96555570003-WATHEFNI-J2P2_PROD_TEST` |
| Adapter | links existing app; does **not** invent application |
| Person | `b938bbb9-b338-5c87-8408-a29a60a3830c` |
| `cv_version` | `4803e737-ef12-50fb-9478-4ddc4b734f94` |
| `application_job_binding` | verified, `position_code=J2P2_PROD_TEST` |
| `application_cv_binding` | pinned to that `cv_version` |
| Shadow gate | **allow** |

### 5) Talent Pool → promote to exact Job

| Check | Evidence |
|---|---|
| Seed | unsolicited WA → TP `a077caee-87fd-58bd-99c0-8af57835b875`, non-actionable; CV `3a689dec-2ecd-57e3-8ac9-2f2565471404` |
| Promote app | `96555570004-WATHEFNI-J2P2_PROD_TEST` |
| Shadow before bind | **shadow_deny** |
| After `promote_with_verified_job_binding` | verified job binding + pinned CV binding |
| Shadow after | **allow** |
| TP row | remains **actionable=false** (Job action via verified binding, not TP actionability) |

---

## Population / mutation summary

| Metric | Before | After |
|---|---|---|
| WATHEFNI applications (non-canary) | 18 | **18** |
| Candidates (non-canary) | 21 | **21** |
| Canary applications | 0 | **2** |
| Total applications | 18 | 20 |
| Verified job bindings | 11 | **13** (+2 canary) |
| Held imports unbound | 2 | **2** |

No unrelated application or candidate mutation. No duplicate canary persons for the four canary phones.

---

## Shadow gate (post-canary)

| Cohort | Expected | Result |
|---|---|---|
| Canary Job apps (2) | allow | **allow** |
| Legacy backfilled live apps (11) | allow (unchanged) | not re-enumerated here; bindings remain |
| Legacy smoke `9655555013x` (5) | shadow_deny | **shadow_deny** |
| Held imports (2) | shadow_deny | **shadow_deny** |

---

## Safety posture preserved

```text
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE=on
WATHEFNI_UNIFIED_JOB_BINDING_AUTHORITY=on
WATHEFNI_UNIFIED_INBOUND_CV_WAVE4=on
# WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE  — NOT SET
```

- Live email path still marked authoritative in `durable_email_ingress.py`
- WhatsApp / manual dual-write adapters additive only (`creates_job_application=false`)
- Health **200** before and after

---

## Final GO / NO-GO for controlled channel cutover

| Item | Decision |
|---|---|
| Forward dual-write canary (5 cases) | **GO (done)** |
| Continue production-dark shadow + bindings | **GO** |
| Controlled **channel cutover** | **NO-GO** |
| Enable **ENFORCE** | **NO-GO** |

Stop condition honored: report only — ENFORCE not enabled; no intake channel cut over.
