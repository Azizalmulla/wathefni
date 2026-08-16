# Pre-hiring Unified Inbound CV — Legacy Job Binding Audited Backfill

Date: 2026-07-27 (Asia/Kuwait) / deploy stamp `20260727T004230Z`  
Prerequisite audits: read-only audit `20260727T003453Z` (accepted); production-dark `20260727T002415Z`  
Host: `root@76.13.63.68`  
Database: `wathefni` (production only)  
Orchestrator: `/opt/wathefni/orchestrator` (`127.0.0.1:8010`)

Evidence:
- Remote: `/opt/wathefni/production-evidence/unified-inbound-cv-legacy-binding-backfill/20260727T004230Z/`
- Local: `ops/screenshots/unified-inbound-cv-legacy-binding-backfill/20260727T004230Z/`
- Backup / rollback: `/opt/wathefni/backups/production-pre-legacy-binding-backfill-20260727T004230Z/`
- Script: `ops/unified-inbound-cv-legacy-binding-backfill.py`
- Deploy: `ops/deploy-unified-inbound-cv-legacy-binding-backfill.sh`

Mutations: **narrow** — only `application_job_bindings` + `intake_consent_events` for the exact 11 allowlisted apps  
`application_cv_bindings`: **0** (no trustworthy CV versions available)  
Enforcement: **OFF** (`WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE` absent)  
Channel cutover: **not performed** (email / WhatsApp / manual stay on current authoritative paths)

---

## Verdict

| Gate | Result |
|---|---|
| Exact 11 allowlist only | **PASS** |
| Exclude 5 smoke + 2 held | **PASS** |
| Per-row company / position / Job / conflict checks | **PASS** |
| Provenance `legacy_backfill=true` | **PASS** (11/11) |
| CV bindings only when trustworthy | **PASS** (0 created; none available) |
| ENFORCE OFF | **PASS** |
| Channels unchanged | **PASS** |
| Shadow: 11 allow / 5 smoke deny / 2 held deny | **PASS** |
| bugs = 0 / unexplained = 0 | **PASS** |
| Health 200 | **PASS** |
| Zero app / candidate mutation (18→18 / 21→21) | **PASS** |
| In-process rollback + re-apply | **PASS** |
| Kill switch (flags file rename) + restore | **PASS** |

### Explicit GO / NO-GO

| Decision | Result |
|---|---|
| Keep production-dark + audited legacy backfill (this task) | **GO / PASS** |
| Controlled channel cutover (email / WhatsApp / manual → envelope authority) | **NO-GO** |
| Enabling `WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE` | **NO-GO** |
| External tenants / Role Profiles | **NO-GO** |

**Why cutover remains NO-GO:** the legacy Job-binding gap for the 11 live apps is closed under shadow, but intake channels were **not** switched, ENFORCE stays **OFF**, and cutover still needs a separate owner authorization plus forward dual-write observation on live channel traffic.

---

## Exact apps backfilled and skipped

### Backfilled (11) — `safe_to_backfill_after_owner_approval`

| app_key | position_code | apply_code | job_id | CV binding |
|---|---|---|---|---|
| `96597727743-WATHEFNI-FULLSTACK_DEVELOPER` | `FULLSTACK_DEVELOPER` | `APPLY-WATHEFNI-FULLSTACK_DEVELOPER` | `824b6a9e-e6fe-4a2d-a795-46d7b90c1d2c` | none |
| `96599338566-WATHEFNI-FULLSTACK_DEVELOPER` | `FULLSTACK_DEVELOPER` | `APPLY-WATHEFNI-FULLSTACK_DEVELOPER` | `824b6a9e-e6fe-4a2d-a795-46d7b90c1d2c` | none |
| `96597727743-WATHEFNI-MARKETING_SPECIALIST` | `MARKETING_SPECIALIST` | `APPLY-WATHEFNI-MARKETING_SPECIALIST` | `5cf8e5d9-4bb3-4645-a771-6b8367b0b395` | none |
| `96550252254-WATHEFNI-SOCIAL_MEDIA_MANAGER` | `SOCIAL_MEDIA_MANAGER` | `APPLY-WATHEFNI-SOCIAL_MEDIA_MANAGER` | `4cb2db97-2294-4059-a56c-f9aa6f75430a` | none |
| `96599652277-WATHEFNI-SOCIAL_MEDIA_MANAGER` | `SOCIAL_MEDIA_MANAGER` | `APPLY-WATHEFNI-SOCIAL_MEDIA_MANAGER` | `4cb2db97-2294-4059-a56c-f9aa6f75430a` | none |
| `96597485758-WATHEFNI-HR` | `HR` | `APPLY-WATHEFNI-HR` | `1350c838-d9bb-4848-84a5-b89ea6d07909` | none |
| `96598900677-WATHEFNI-ACCOUNTING` | `ACCOUNTING` | `APPLY-WATHEFNI-ACCOUNTING` | `8f08acad-1cd3-4651-a307-96d04d454eb2` | none |
| `96598900677-WATHEFNI-FINANCE` | `FINANCE` | `APPLY-WATHEFNI-FINANCE` | `3ca7ad6a-9726-48d9-8b9c-3cab473bda90` | none |
| `96598900677-WATHEFNI-HR` | `HR` | `APPLY-WATHEFNI-HR` | `1350c838-d9bb-4848-84a5-b89ea6d07909` | none |
| `96566363363-WATHEFNI-IT_MAINTENANCE` | `IT_MAINTENANCE` | `APPLY-WATHEFNI-IT_MAINTENANCE` | `7821c69b-5ed1-4036-86eb-04512d79afee` | none |
| `96597485758-WATHEFNI-ACCOUNTING_EXCEL` | `ACCOUNTING_EXCEL` | `APPLY-WATHEFNI-ACCOUNTING_EXCEL` | `df841f68-95b1-4ac1-b60e-f985424952a2` | none |

Pass1: **11 created / 0 skipped / 0 rejected**  
Pass2 (after rollback proof): **11 created / 0 skipped / 0 rejected**

### Explicitly skipped / excluded (7)

| app_key | reason |
|---|---|
| `96555550132-WATHEFNI-ACCOUNTING` | smoke_test / quarantined — never backfilled |
| `96555550133-WATHEFNI-ACCOUNTING` | smoke_test / quarantined — never backfilled |
| `96555550134-WATHEFNI-ACCOUNTING_EXCEL` | smoke_test / quarantined — never backfilled |
| `96555550135-WATHEFNI-ACCOUNTING_EXCEL` | smoke_test / quarantined — never backfilled |
| `96555550136-WATHEFNI-ACCOUNTING_EXCEL` | smoke_test / quarantined — never backfilled |
| `imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT` | held `needs_role` Talent Pool — never backfilled |
| `imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT` | held `needs_role` Talent Pool — never backfilled |

---

## Evidence used (per-row gates)

For each allowlisted app, preflight required all of:

1. `company_code = WATHEFNI`
2. Exact canonical `position_code` present on the application
3. Matching canonical Job row in `positions` (same `position_code`; apply_code consistent when both set)
4. No conflicting verified `application_job_bindings` for a different position
5. Not held (`needs_role` / `import_review` / `import_archived`), not smoke/quarantined, not missing position
6. App key present in the accepted audit allowlist only

CV binding gate (separate): create `application_cv_bindings` only when exactly one trustworthy ready `cv_versions` row is owned by `legacy_app_key`, **or** exactly one current ready `candidate_cv_text_versions` row for the app.  
**Result:** no allowlisted app met that bar → **0 CV bindings**.

Provenance on each job binding includes:

```json
{
  "legacy_backfill": true,
  "source": "legacy_binding_backfill",
  "audit_stamp": "20260727T003453Z",
  "classification": "safe_to_backfill_after_owner_approval",
  "cv_binding_created": false
}
```

Consent: `intake_consent_events.consent_kind = legacy_backfill` (one per bind), actor `legacy-binding-backfill`.

---

## Bindings created (final state)

| Table | Count | Notes |
|---|---|---|
| `application_job_bindings` (WATHEFNI verified) | **11** | all `provenance.legacy_backfill = true` |
| `application_cv_bindings` (allowlist) | **0** | no trustworthy CV versions |
| `intake_consent_events` (`legacy_backfill`) | **11** | after final re-apply |
| WATHEFNI `applications` | **18** (unchanged) | no inserts/duplicates |
| `candidates` | **21** (unchanged) | no mutation |

Before → after verified job bindings: **0 → 11**.

---

## Shadow observation before / after

In-process gate scan with SHADOW env (`GATE` + `SHADOW` on, ENFORCE unset).

### Before backfill

| Classification | Count |
|---|---|
| `valid_legacy_application_needing_audited_backfill` | **11** (allowlist, `shadow_deny` / `verified_job_binding_missing`) |
| `expected_missing_verified_binding` | **7** (5 smoke + 2 held) |
| `bug` | **0** |
| `unexplained` | **0** |

### After in-process rollback (bindings deleted)

Same as before: **11** needing backfill + **7** expected missing — proves rollback restored the pre-backfill shadow posture.

### After final re-apply

| Classification | Count |
|---|---|
| `allow_verified_binding` | **11** (allowlist all `mode=allow`) |
| `expected_missing_verified_binding` | **7** (5 smoke + 2 held all `mode=shadow_deny`) |
| `bug` | **0** |
| `unexplained` | **0** |

Assertions (`backfill.json`):

```text
allowlist_all_allow: true
smoke_all_shadow_deny: true
held_all_shadow_deny: true
bugs: 0
unexplained: 0
zero_app_mutation: true
zero_candidate_mutation: true
job_bindings_created: 11
cv_bindings_created: 0
ok: true
```

Health: **200** pre, post-kill-restore, and final (`final-health.txt`).

---

## Rollback proof

1. **Pre-backfill dump:**  
   `/opt/wathefni/backups/production-pre-legacy-binding-backfill-20260727T004230Z/bindings.dump`  
   (tables: `application_job_bindings`, `application_cv_bindings`, `intake_consent_events`)

2. **Scripted rollback helper:**  
   `/opt/wathefni/backups/production-pre-legacy-binding-backfill-20260727T004230Z/ROLLBACK_BACKFILL.sh`  
   Deletes only allowlisted rows with `provenance.legacy_backfill=true` plus matching `legacy_backfill` consents.

3. **In-process proof (executed):**  
   - Pass1 created 11 job bindings + 11 consents  
   - Delete removed `job_bindings_deleted=11`, `consents_deleted=11`, `cv_bindings_deleted=0`  
   - Shadow returned to pre-backfill counts  
   - Pass2 re-created the same 11 bindings  

Bindings are reversible without touching applications, candidates, or channel paths.

---

## Kill switch proof

Same production-dark mechanism: rename `/opt/wathefni/var/unified-inbound-cv.production.env`, restart, restore.

| Step | Evidence |
|---|---|
| Kill | Flags file renamed; Wave4 / verified-binding unified flags absent from process env (`kill-switch-flags.txt` empty for those keys) |
| Restore | `production-flags-restored.txt` shows SHADOW=`on`, GATE=`on`, dual-writes restored |
| ENFORCE | Still **absent** after restore |
| Health | **200** after restore (`post-kill-restore-health.txt`) |
| Marker | `kill-switch-proof.txt` → `KILL_SWITCH_OK` |

Kill switch disables the unified dual-write / shadow feature flags; it does **not** delete the 11 backfilled binding rows (data remains; gate simply stops observing/enforcing until flags return). Data rollback remains `ROLLBACK_BACKFILL.sh`.

---

## What did not change

- `WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE` — **not set**
- Email / WhatsApp / manual intake — **still authoritative on current paths**
- Application count — **18**
- Candidate count — **21**
- Smoke-test and held apps — **still unbound**

---

## Final GO / NO-GO for controlled channel cutover

| Item | Decision |
|---|---|
| Audited legacy backfill of the 11 safe apps | **GO (done)** |
| Continue production-dark shadow observation with bindings in place | **GO** |
| Controlled **channel cutover** | **NO-GO** |
| Enable **ENFORCE** | **NO-GO** |

Stop condition honored: report only — ENFORCE not enabled; no intake channel cut over.
