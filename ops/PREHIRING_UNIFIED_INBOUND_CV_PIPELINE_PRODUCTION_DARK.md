# Pre-hiring Unified Inbound CV Pipeline — WATHEFNI Production-Dark

Date: 2026-07-27 (Asia/Kuwait) / stamp `20260727T002415Z`  
Prerequisite: Wave 4 accepted  
Host: `root@76.13.63.68`  
Database: `wathefni` (production only)  
Orchestrator: `/opt/wathefni/orchestrator` (`127.0.0.1:8010`)

Evidence:
- Remote: `/opt/wathefni/production-evidence/unified-inbound-cv-dark/20260727T002415Z/`
- Local: `ops/screenshots/unified-inbound-cv-production-dark/20260727T002415Z/`
- Backup / rollback: `/opt/wathefni/backups/production-pre-unified-inbound-cv-dark-20260727T002415Z/`

Deploy: `ops/deploy-unified-inbound-cv-production-dark.sh`  
Observe: `ops/unified-inbound-cv-production-dark-observe.py`  
Patcher: `ops/patch-production-app-unified-inbound-cv-dark.py` (surgical; no full `app.py` replace)

---

## Verdict

| Gate | Result |
|---|---|
| Fresh production backup + hashes | **PASS** |
| Additive Wave 1–4 modules + production drop-in | **PASS** |
| Surgical `app.py` patch only | **PASS** |
| Dual-write + shadow gate enabled; **ENFORCE OFF** | **PASS** |
| Channel cutovers OFF; email/WhatsApp/manual authoritative | **PASS** |
| Bounded observations (email / manual / WA unsolicited / WA job) | **PASS** (28/28) |
| Zero duplicate candidates/apps; zero downstream mutation | **PASS** (21→21 / 18→18) |
| Health 200 (prod + staging) | **PASS** |
| Kill switch + rollback proof | **PASS** |
| Shadow denials classified (0 bug / 0 unexplained) | **PASS** |

### Explicit GO / NO-GO

| Decision | Result |
|---|---|
| WATHEFNI **production-dark** (this task) | **GO / PASS** |
| Controlled channel cutover (email / WhatsApp / manual → envelope authority) | **NO-GO** |
| Enabling `WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE` | **NO-GO** |
| External tenants | **NO-GO** |
| Role Profiles | **NO-GO** |

**Controlled cutover remains NO-GO** until an audited legacy Job-binding backfill exists for live applications (16/18 sampled apps are valid legacy rows missing verified bindings) and a separate owner authorization covers cutover.

---

## 1) Exact flags

Final safe production-dark posture (`/opt/wathefni/var/unified-inbound-cv.production.env`):

```text
WATHEFNI_UNIFIED_INTAKE_ENVELOPE_DUAL_WRITE=on
WATHEFNI_UNIFIED_CV_VERSION_DUAL_WRITE=on
WATHEFNI_UNIFIED_CV_PROCESSING_STAGE_LEDGER=on
WATHEFNI_UNIFIED_INBOUND_CV_ADAPTERS=on
WATHEFNI_UNIFIED_ADAPTER_SHARED_PROCESSING=on
WATHEFNI_UNIFIED_INBOUND_CV_WAVE4=on
WATHEFNI_UNIFIED_PERSON_REGISTRY_DUAL_WRITE=on
WATHEFNI_UNIFIED_TALENT_POOL_ENTRIES=on
WATHEFNI_UNIFIED_CK_PERSON_SUBJECT_REFS=on
WATHEFNI_UNIFIED_JOB_BINDING_AUTHORITY=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on
# WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE  — NOT SET
```

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/unified-inbound-cv.conf`  
(`EnvironmentFile=-/opt/wathefni/var/unified-inbound-cv.production.env`)

Verified live process: `WAVE4=on`, `SHADOW=on`, `ENFORCE` **absent**.

---

## 2) Artifact / config / schema hashes

### Pre-deploy (`PREDEPLOY.txt`)

| Artifact | sha256 |
|---|---|
| `app.py` | `eddf2ff6b6fb4230df096f79c591c0d58890c37d54cdb00b528f235e176f4270` |
| `durable_email_ingress.py` | `0257f8fb4ebc5bc70e33b2775ae7338f1a06b67f1cdceea18042365f54d0ab66` |
| `action_registry.py` | `7c3d2ef8a7db27c95883b5997797b97ca8a980792c52a1179b5520b09ed1aaf6` |

### Post-deploy (`artifact.sha256`)

| Artifact | sha256 |
|---|---|
| `app.py` (surgically patched) | `1e51fadecbd5a6ebb17b74ffef28938c7b939b747dba31fb0e7f5cccb588b868` |
| `durable_email_ingress.py` | `908381b92aef24dc64743c921b92cd9b3e54a0193f1932636ec95e6bcf9df1e7` |
| `inbound_cv_intake.py` | `d4bad0838c7757431d267ebb27b4941c85acdf7c7173b546bfca33b2fa0ccdb9` |
| `inbound_cv_processing.py` | `7538c93995df941e879b2ebb32ce6916b2cc96f53f5d62ea839e6fb9d93dd19c` |
| `inbound_cv_adapters.py` | `cbeca2f59b39c453472d88cde4519f8c40105122dc3fc63184e28dd69a79278d` |
| `inbound_cv_person_registry.py` | `2953d58575d96fb2ca58f7b4f3caab34460f02c8288ef89efc1353240bba261b` |
| `inbound_cv_wave4.py` | `3044dca8e97765468775c7cd65c48be70acca802c613fd2494329687d0f2822d` |
| `talent_pool_authority.py` | `4eae7a4a3ac419716ee7dd5f75a3ee2c86789686bf8a9849535eb44344ef7a14` |
| `job_binding_authority.py` | `2df710ea9365eab906bbee5539e1d8588a57ce0e8ea14c32bae3be1c2d5201a8` |
| `verified_job_binding_gate.py` | `9747a89738957607580eb19944f5df3ec053760e82bc1a013388d95459692435` |
| `candidate_knowledge_wave4.py` | `71ae08f3b236935196b4e1faaf8527494a9fe1817c871346c8d87ea37a2fd52c` |
| `candidate_knowledge_types.py` | `bc0c37971a98f1e19e573dafba2a435c86124faf7fe0b075f5a756487b9b73a1` |
| `candidate_knowledge_authority.py` | `f5a4ae70e200a087b99bc069dfbebce52f7346bf024362ac81bdcab444c1aba1` |
| flags env | `986b9a4bb4067cf1ecb8b277b32b0b7c58a0be3823121fbd52efde6d0a5c581d` |
| drop-in conf | `c549f5113c76e58215cc740839f4c9d8df2b81c3b52985e20bf3ab38414868ab` |

### Backup

| Item | Value |
|---|---|
| DB dump | `…/db.dump` (~5.5 MB, custom format) + `db.restore-list` |
| Rollback script | `ROLLBACK.sh` (**executable**) |
| Pre-health | **200** |

### Surgical patch actions

```json
{"ok": true, "actions": ["schema_ensure", "manual_adapter", "wa_unsolicited", "wa_job", "wave4_gate"]}
```

---

## 3) Schema and dual-write parity

Additive tables present after dark observation:

`intake_source_events`, `intake_subjects`, `intake_items`, `cv_versions`, `cv_processing_stage_runs`, `talent_pool_entries`, `application_job_bindings`, `application_cv_bindings`, `intake_consent_events`

| Observation | Result |
|---|---|
| Email envelope dual-write + replay stable event id | **PASS** |
| Manual adapter (held; no Job create) | **PASS** |
| Unsolicited WhatsApp adapter (HR-visible non-actionable) | **PASS** |
| Job WhatsApp adapter (links only; no Job create) | **PASS** |
| `cv_version` idempotent (1 row for digest+document) | **PASS** |

Post-observation additive counts (bounded dark writes only): events/TP/CV ≈ 4 each; **candidates 21**, **applications 18** unchanged.

---

## 4) Identity / Talent Pool / CV-version

| Check | Result |
|---|---|
| Person Registry link (`linked`, no merge) | **PASS** |
| Talent Pool entry non-actionable | **PASS** |
| Person/subject-owned `cv_version` | **PASS** |
| Membership reuse does not create duplicate TP rows | **PASS** (fix mid-flight; redeployed) |
| Cross-tenant person seed isolation | **PASS** |

---

## 5) CK person / subject

| Check | Result |
|---|---|
| `person:` parse/resolve when flag ON | **PASS** |
| `subject:` parse/resolve when flag ON | **PASS** |
| `app:` compatibility | **PASS** |
| Searchable non-actionable Talent Pool actionability | **PASS** |
| Index meta (`ref_kind=person`, non-actionable) | **PASS** |
| Live CK tools / Ranking reader / Voyage cutover | **still OFF** (unchanged) |

---

## 6) Shadow-deny counts and classifications

Bounded sample: latest **18** WATHEFNI applications (cap 50).

| Classification | Count |
|---|---|
| `expected_missing_verified_binding` (held / unassigned Talent Pool) | **2** |
| `valid_legacy_application_needing_audited_backfill` | **16** |
| `malformed_orphan_application` | **0** |
| `bug` | **0** |
| `unexplained` | **0** |
| `allow_verified_binding` | **0** |

Interpretation: shadow denials are **expected** during production-dark. Live Job apps lack `application_job_bindings` until audited backfill or forward dual-write on new exact confirms. Held imports correctly shadow-deny without mutating behavior (enforce OFF).

Samples retained in `observation.json` (`shadow_samples`).

---

## 7) Zero-mutation proof

| Metric | Before → After |
|---|---|
| `candidates` | 21 → **21** |
| `applications` | 18 → **18** |
| Duplicate `cv_versions` for observation digest | **1** (no dup) |
| Downstream ranking/screening/offer behavior | unchanged (shadow only) |
| Email authoritative path marker present | **PASS** |

---

## 8) Rollback and kill-switch proof

| Proof | Result |
|---|---|
| Automatic rollback on earlier failed attempts (health restored 200) | **PASS** |
| `ROLLBACK.sh` present + executable for this stamp | **PASS** |
| Kill switch: rename flags file → Wave4/gate keys absent → restore | **PASS** (`KILL_SWITCH_OK`; empty `kill-switch-flags.txt`) |
| Health after kill + restore | **200** |
| Final ENFORCE absent | **PASS** |

Note: systemd `EnvironmentFile=` overrides `Environment=`; kill-switch therefore removes/renames the flags file rather than relying on a later drop-in `Environment=off`.

---

## 9) Incidents during this migration (contained)

1. **Talent Pool membership unique** — first observation failed when email + WhatsApp reused one membership across subjects. Fixed `talent_pool_authority.upsert_talent_pool_entry` to reuse by membership; auto-rollback restored production; redeployed.
2. **Kill-switch drop-in order / EnvironmentFile precedence** — corrected to flags-file rename proof.

Neither incident left ENFORCE on or channel cutover enabled.

---

## Final GO / NO-GO for controlled channel cutover

| Decision | Result |
|---|---|
| Keep production-dark dual-write + shadow observation | **GO** |
| Controlled cutover of email / WhatsApp / manual intake | **NO-GO** |
| Enable verified-binding **ENFORCE** | **NO-GO** |

Cutover blockers:
1. Audited backfill plan for legacy live apps missing verified bindings (16 in sample).
2. Separate owner authorization for channel authority cutover.
3. Sustained shadow observation window with no unexplained/bug classifications on organic traffic.

**Stop after this report. Enforcement not enabled. Channels not cut over.**
