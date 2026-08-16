# Kuwait First-Client Foundation — Local Remediation

**Date:** 2026-07-25  
**Mode:** contained local remediation — **do not deploy**  
**Status:** local-qualified · **not** staging-promoted · **not** production-installed  
**Upstream authority:** `ops/KUWAIT_PRIVATE_SECTOR_REQUIREMENTS_RESEARCH.md` (approved)  
**Compared against:** `ops/KUWAIT_GCC_COUNTRY_PACK_READINESS_AUDIT.md`  
**Local evidence:** `ops/kuwait-first-client-foundation/kuwait-first-client-foundation-local-20260725T030934Z.json`  
**Harness:** `ops/kuwait-first-client-foundation/kuwait-first-client-foundation-local-matrix.py`  
**SOE module:** `wathefni-orchestrator/kuwait_first_client_foundation.py`  
**Hire hook:** `wathefni-orchestrator/hire_operations.py` → `_employee_transaction`  

---

## Verdict

Local remediation for the verified Kuwait first-client foundation is **complete and locally green (44/44)**.

This work delivers:

1. tenant-scoped **legal-entity** master with one active default;  
2. atomic hire-time **employment-applicability snapshot**;  
3. governed **employee identity** vs **document metadata** split;  
4. Kuwait **`residence` / `work_permit` / `article_18`** vocabulary with non-destructive `residency_iqama` compatibility;  
5. **Arabic employment-contract upload** path linked immutably to the snapshot.

**Do not claim automatic Kuwait legal compliance.** This foundation stores employer-entered records, counsel-reviewed upload contracts, and hire-time applicability — it does **not** enforce leave law, EOS/PIFSS, fines, statutory OT multipliers, payroll payments, or PAM/MOI/PACI filings.

**Do not deploy.** Production hire path must remain on the frozen Offers/Hiring green pin until an explicit staging → production promote.

---

## Pilot scope (locked)

| In | Out |
|---|---|
| Kuwait private-sector employers | Automatic legal compliance claims |
| Kuwaiti nationals + Article 18 expatriates | Leave-law / EOS / PIFSS calculations |
| Employer-configured document requirements | Fine calculations / statutory OT multipliers |
| Counsel-reviewed Arabic Unicode PDF upload | Payroll payments |
| Employer-entered government identifiers (text) | PAM / MOI / PACI API verification or filings |
| Article 80 operational file anchors | Country-pack branding as legal authority |

---

## Evidence → requirement traceability

| Research / audit need | Source | Foundation delivery | Qual gate(s) |
|---|---|---|---|
| E1/E5 — registered entity + CR/licence as employer text | Research §1.1 | `legal_entities` EN/AR names, CR, licence, PAM file no. | `arabic_and_english_legal_names`, `default_legal_entity_exactly_one` |
| Exactly one default active legal entity | Research §4 / pilot | Partial unique index `legal_entities_one_default_uq` | `default_legal_entity_exactly_one`, `default_entity_uniqueness_after_switch` |
| Multiple entities allowed; history retains binding | Research E5 | Snapshots FK `legal_entity_id`; entity switch does not rewrite | `multiple_legal_entities_allowed`, `entity_switch_does_not_rewrite_snapshot` |
| Art. 80 file: contract, Civil ID, work permit, leave/OT | Research Art. 80 | Snapshot + identity + document metadata + existing leave/OT systems (unchanged) | snapshot + identity + metadata gates |
| I1 Civil ID sensitive + masked | Research I1 | Encrypted storage; mask default; `read_full` reveal | `civil_id_masked_by_default`, `civil_id_full_reveal_privileged` |
| I2/I5 nationality + category KW vs Art. 18 | Research I2/I5 | `employee_category` + `nationality_country_code` | national/expat hire gates |
| I4 Article 18 — not iqama | Research terminology | Canonical `residence`; `article_18_expatriate` | `no_iqama_canonical_token`, `normalize_residence_*` |
| I6 police/blood/lease not master | Research I6 | Blocked from `employee_document_metadata` | `gov_attachments_blocked_as_master`, `police_certificate_not_master_metadata` |
| Hire-time applicability from offer authority | Audit gap / Research | Snapshot from accepted offer / offers-off defaults / hire override | `snapshot_from_accepted_offer`, `offers_disabled_*`, `hire_override_*` |
| Atomic hire; no duplicate employee/snapshot | Offers/Hiring frozen contract | Same TX as employee INSERT; `UNIQUE(company_code, employee_key)` | `replay_hire_*`, `concurrent_hire_*` |
| Arabic contract upload (not generated text) | Research / pilot | `link_arabic_contract_to_snapshot` metadata only | `arabic_contract_linked`, `arabic_contract_metadata_complete` |
| Historical `residency_iqama` readable | Terminology rule | Compat map; no destructive merge | `historical_residency_iqama_still_readable`, `compat_maps_legacy_to_residence` |
| Nationals: no residence/work permit required | Research I5 | Category seed + requiredness | `national_seed_no_residence`, `national_compliance_no_residence_or_work_permit` |
| Expats: residence + work permit tracking | Research I3/I4 | Seed + document metadata | `expat_seed_has_residence_and_work_permit`, `expat_compliance_*` |
| OCR non-authoritative until HR confirm | Pilot identity rules | `ocr_pending` + `*_confirmed` flags | `ocr_not_authoritative_until_confirm` |
| Tenant isolation | Platform baseline | All tables keyed by `company_code` | `tenant_isolation_*` |

---

## Schema and authority map

```
companies (tenant)
    │
    ├── legal_entities ─────────────── legal_entity_events (append-only)
    │         ▲
    │         │ FK (immutable after hire)
    │         │
    ├── employment_applicability_snapshots ── employment_applicability_events
    │         ▲ created once at canonical hire (same TX as employees)
    │         │ UNIQUE(company_code, employee_key)
    │         │
    ├── employees  ◄── hire_operations (frozen hire authority unchanged)
    │
    ├── employee_identity ──────────── employee_identity_events (field-level)
    │
    ├── employee_document_metadata ─── (never master; gov-process types blocked)
    │
    ├── document_type_compat_map ───── residency_iqama|residency → residence
    │
    ├── compliance_documents ───────── category-aware seed (existing product)
    └── onboarding items ───────────── new seeds use `residence` (legacy rows kept)
```

**Authority stack (hire):**

| Layer | Role |
|---|---|
| Accepted offer / version (or offers-disabled defaults / hire override) | **Terms authority** — frozen; not replaced |
| `employment_applicability_snapshots` | **Applicable employment terms** at hire — immutable core |
| Country-pack branding / labels | **Not** legal authority |
| `legal_entities` | Employer file identity; snapshot binds the entity used at hire |
| `employee_identity` | Authoritative identifiers only after HR confirmation |
| `employee_document_metadata` / compliance / onboarding | Documents and reminders — not nationality/status inference |

---

## 1. Legal-entity contract

### Fields

| Field | Type | Notes |
|---|---|---|
| `legal_entity_id` | uuid PK | Stable |
| `company_code` | text | Tenant scope |
| `country_code` | char(2) | Pilot default `KW` |
| `registered_name_en` | text | Required |
| `registered_name_ar` | text | Required for bilingual employers |
| `commercial_registration_no` | text | Employer-entered; not API-verified |
| `licence_no` | text | Employer-entered |
| `pam_employer_file_no` | text | Employer-entered PAM/file reference |
| `default_currency` | text | Default `KWD` |
| `status` | `active` \| `inactive` | |
| `is_default` | boolean | Exactly one **active** default per tenant |

### Rules

- Every Kuwait pilot tenant has **exactly one** default **active** legal entity (enforced by unique partial index).  
- Multiple legal entities may exist.  
- No government verification, accounting, tax, payroll, or intercompany logic.  
- Historical employment snapshots retain original `legal_entity_id`.  
- All mutations append to `legal_entity_events`.

### Permissions

- `employees.legal_entity.read`  
- `employees.legal_entity.manage`

---

## 2. Employment-applicability snapshot contract

Created **atomically** with the employee row inside `_employee_transaction`. Exactly one row per `(company_code, employee_key)`.

### Captured fields

| Field | Meaning |
|---|---|
| `country_of_employment` | From offer/defaults |
| `legal_entity_id` | Default (or override) entity at hire |
| `currency` | Hire currency |
| `accepted_offer_id` / `accepted_offer_version` | When source is accepted offer |
| `template_id` / `template_version` / `template_approval_ref` | Contract template governance |
| `document_language` | e.g. `ar` / `en` |
| `employer_policy_version` | When explicitly selected |
| `configuration_effective_date` | Policy/config effective date |
| `proposed_start_date` | Proposed start |
| `probation_days` | When present |
| `compensation_snapshot` | Immutable JSON copy / reference payload |
| `source_path` | `accepted_offer` \| `offers_disabled_defaults` \| `hire_override` |
| `hire_operation_id` / `app_key` | Audit link to hire |
| `arabic_contract_file_id` / `arabic_contract_metadata` | Upload link (post-hire attach allowed; core terms unchanged) |
| `snapshot_hash` | Content hash of core applicability payload |
| `created_at` | Snapshot timestamp |

### Rules

- Does **not** replace frozen offer or hire authority.  
- Concurrent / replayed hire creates **no** duplicate employee or snapshot.  
- Future policy/template/entity changes must **not** silently rewrite existing snapshot cores (`entity_switch_does_not_rewrite_snapshot`, `snapshot_core_immutable_after_contract_link`).  
- Append-only `employment_applicability_events` for attach/audit actions.

---

## 3. Employee-master vs document-metadata matrix

| Concept | Employee master (`employee_identity`) | Document metadata | Onboarding / compliance attachment only |
|---|---|---|---|
| Civil ID number | **Yes** (encrypted; confirmed) | Expiry / issuer / file on metadata | — |
| Nationality country code | **Yes** (employer-entered; no inference) | — | — |
| Employee category (`kuwaiti_national` / `article_18_expatriate` / `other` / `unspecified`) | **Yes** | — | — |
| Passport number | **Yes** when required | Issue/expiry/file | — |
| Residence number | **Yes** when required (Art. 18) | Issue/expiry/file | — |
| Work-permit number | **Yes** when required | Issue/expiry/file | — |
| Issuing authority / issue / expiry / file / verification / HR reviewer / source / notes | — | **Yes** | — |
| Police certificate / blood test / lease / fingerprint notice | **Forbidden** | **Forbidden as metadata master** | **Yes** (transient checklist only) |

### Default requiredness by category

| Field | Kuwaiti national | Article 18 expatriate | other / unspecified |
|---|---|---|---|
| Civil ID | Required | Required | Employer policy |
| Nationality | Required | Required | Employer policy |
| Passport | Not required | Required | Employer policy |
| Residence number | Not required | Required | Employer policy |
| Work-permit number | Not required | Required | Employer policy |

Employers may override requiredness via `requiredness_policy` JSON; product does not infer nationality or legal status.

### Compliance seed (hire)

| Category | Seeded compliance types |
|---|---|
| `kuwaiti_national` | `civil_id` |
| `article_18_expatriate` | `civil_id`, `passport`, `residence`, `work_permit` |
| unspecified / other | `civil_id`, `passport` (no residence/work permit forced) |

---

## 4. Residence compatibility strategy

| Legacy id | Canonical | Merge behaviour |
|---|---|---|
| `residency_iqama` | `residence` | **Read via compat**; row type preserved historically |
| `residency` | `residence` | Same |
| `residence` | `residence` | New Kuwait writes |

**Prove / policy:**

- Historical rows remain readable (`historical_residence_types()` includes all three).  
- `document_type_compat_map` records explicit mapping — **no silent destructive UPDATE** of legacy document_type values.  
- New Kuwait seeds / uploads use `residence`.  
- Saudi `iqama` is **not** a canonical Kuwait token (`no_iqama_canonical_token`).  
- Expat onboarding → compliance includes `residence` + `work_permit`.  
- National workflows do not require residence/work-permit records.

---

## 5. Arabic employment-contract path

Upload-based only for this phase (no generated Arabic legal text).

Required metadata on link:

- counsel/employer-approved Arabic Unicode PDF (`file_id`);  
- `template_id` + `template_version`;  
- `approval_ref`;  
- `document_language` (`ar`);  
- `effective_date`;  
- authorized signatory metadata;  
- immutable snapshot link (`arabic_contract_file_id` + `arabic_contract_metadata`);  
- RTL/Arabic readability is an operational verification checklist item for staging UI (local matrix asserts metadata completeness and snapshot core immutability).

---

## Sensitive-data permissions

| Permission | Effect |
|---|---|
| `employees.identity.read` | Masked identifiers + category/nationality; OCR pending keys only |
| `employees.identity.read_full` | Full decrypt reveal |
| `employees.identity.write` | Category, confirm OCR → authoritative, direct edits |

Storage: Fernet when `WATHEFNI_CIVIL_ID_KEY` is a Fernet key; HMAC stream fallback otherwise. Field-level events in `employee_identity_events`. Tenant isolation via `company_code` primary key.

OCR path: `stage_ocr_identity_value` → `ocr_pending` only → `confirm_identity_field` promotes to encrypted authoritative fields.

---

## Migration and backfill plan

**Local / staging (when authorized — not this step):**

1. Deploy module file + hire hook + `ensure_foundation_schema` via normal schema ensure (no separate destructive migration).  
2. For each Kuwait pilot tenant: `ensure_default_legal_entity(...)` with counsel-supplied EN/AR names and CR/licence/PAM text.  
3. **Do not** bulk-rewrite historical `residency_iqama` compliance/onboarding rows; rely on compat map + normalize helpers.  
4. Optionally backfill `employee_identity.employee_category` only with **explicit employer confirmation** — never infer from name/passport.  
5. Existing employees hired before foundation: create snapshot **only** via audited backfill job (out of pilot P0) — default leave them without inventing terms.  
6. Verify `WATHEFNI_CIVIL_ID_KEY` present before enabling identity write UI.

**Production:** blocked until staging green + owner promote instruction.

---

## Full qualification matrix

**Evidence artifact:** `ops/kuwait-first-client-foundation/kuwait-first-client-foundation-local-20260725T030934Z.json`  
**Result:** **44 passed / 0 failed**  
**Isolation:** throwaway `kw_foundation_*` schemas; rolled back / dropped — **zero residue**  
**Environment:** isolated local tree (`/tmp/kw-foundation-qual`); **not** systemd production import path  

| # | Scenario | Gate | Result |
|---|---|---|---|
| 1 | Normalize `residency_iqama` → `residence` | `normalize_residence_from_residency_iqama` | PASS |
| 2 | Normalize `residency` → `residence` | `normalize_residence_from_residency` | PASS |
| 3 | Canonical `residence` | `normalize_residence_canonical` | PASS |
| 4 | No Saudi iqama as canonical | `no_iqama_canonical_token` | PASS |
| 5 | Gov attachments blocked as master | `gov_attachments_blocked_as_master` | PASS |
| 6 | National seed excludes residence/WP | `national_seed_no_residence` | PASS |
| 7 | Expat seed includes residence+WP | `expat_seed_has_residence_and_work_permit` | PASS |
| 8 | Exactly one default legal entity | `default_legal_entity_exactly_one` | PASS |
| 9 | Arabic + English legal names | `arabic_and_english_legal_names` | PASS |
| 10 | Multiple legal entities | `multiple_legal_entities_allowed` | PASS |
| 11 | Default uniqueness after switch | `default_entity_uniqueness_after_switch` | PASS |
| 12 | Kuwaiti national accepted-offer hire | `accepted_offer_hire_ok` | PASS |
| 13 | Snapshot for national | `snapshot_created_for_national` | PASS |
| 14 | Snapshot source = accepted_offer | `snapshot_from_accepted_offer` | PASS |
| 15 | Snapshot binds legal entity | `snapshot_binds_legal_entity` | PASS |
| 16 | Offer version captured | `snapshot_has_offer_version` | PASS |
| 17 | OCR non-authoritative until confirm | `ocr_not_authoritative_until_confirm` | PASS |
| 18 | Civil ID masked by default | `civil_id_masked_by_default` | PASS |
| 19 | Privileged full reveal | `civil_id_full_reveal_privileged` | PASS |
| 20 | National compliance without residence/WP | `national_compliance_no_residence_or_work_permit` | PASS |
| 21 | Article 18 expat hire | `expat_hire_ok` | PASS |
| 22 | Expat residence metadata canonical | `expat_residence_metadata_canonical` | PASS |
| 23 | Expat work-permit metadata | `expat_work_permit_metadata` | PASS |
| 24 | Police cert rejected as master metadata | `police_certificate_not_master_metadata` | PASS |
| 25 | Expat compliance has residence+WP | `expat_compliance_has_residence_and_work_permit` | PASS |
| 26 | Historical `residency_iqama` readable | `historical_residency_iqama_still_readable` | PASS |
| 27 | Compat map legacy → residence | `compat_maps_legacy_to_residence` | PASS |
| 28 | Arabic contract linked to snapshot | `arabic_contract_linked` | PASS |
| 29 | Arabic contract metadata complete | `arabic_contract_metadata_complete` | PASS |
| 30 | Snapshot core immutable after contract link | `snapshot_core_immutable_after_contract_link` | PASS |
| 31 | Replay hire → one employee | `replay_hire_one_employee` | PASS |
| 32 | Replay hire → one snapshot | `replay_hire_one_snapshot` | PASS |
| 33 | Replay idempotent outcome | `replay_reported_ok_or_idempotent` | PASS |
| 34 | Concurrent hire → single employee | `concurrent_hire_single_employee` | PASS |
| 35 | Concurrent hire → single snapshot | `concurrent_hire_single_snapshot` | PASS |
| 36 | Tenant isolation — legal entities | `tenant_isolation_legal_entities` | PASS |
| 37 | Tenant isolation — identity | `tenant_isolation_identity` | PASS |
| 38 | Entity switch does not rewrite snapshot | `entity_switch_does_not_rewrite_snapshot` | PASS |
| 39 | Offers-disabled hire | `offers_disabled_hire_ok` | PASS |
| 40 | Offers-disabled source path | `offers_disabled_source_path` | PASS |
| 41 | Offers-disabled uses default entity | `offers_disabled_uses_default_entity` | PASS |
| 42 | Offers-disabled template from defaults | `offers_disabled_template_from_defaults` | PASS |
| 43 | Audited hire override | `hire_override_ok` | PASS |
| 44 | Hire-override source path | `hire_override_source_path` | PASS |

### Frozen pre-hiring / post-hire authority regressions

| Suite | Status relative to this remediation |
|---|---|
| Offers/Hiring production-green (`ops/PREHIRING_OFFERS_HIRING_PRODUCTION_GREEN.md`) | **Unchanged on production** — live service was **not** left on foundation code; hire authority pin remains prior green artifact |
| Final pre-hiring production requal | **Not re-opened**; foundation is additive local module |
| Post-hire authority matrices | **Not executed against production** (deploy forbidden) |

**Staging requirement before any promote:** re-run frozen Offers/Hiring + applicable post-hire matrices against a staging build that includes this foundation, with process-local dry-run delivery only.

---

## Residual legal / counsel decisions

| Topic | Why residual | Product stance until counsel |
|---|---|---|
| Leave accrual / annual leave eligibility months | Research UC on Art. 70 amendments | Keep leave preset `enforced=false` |
| EOS / PIFSS vs indemnity pathways | Nationality / GCC edge cases | No calculations |
| Statutory OT multipliers / fines | Not in pilot | Attendance OT remains employer policy modes only |
| Civil ID checksum algorithm | Counsel-approved V only | Store + mask; no PACI verify |
| PAM quota / Kuwaitisation | Outside software P0 | Optional note fields only |
| Family residence (Art. 22) etc. | Not employee work category default | Do not auto-classify |
| Generated Arabic contract text | Separate qualification | Upload path only |
| Backfill snapshots for pre-foundation hires | Historical completeness vs inventing terms | Manual/audited job only when requested |

---

## Staging deployment order

**Do not execute until owner authorizes staging.**

1. **Backup** staging DB + code tree; record pin SHA.  
2. Install `kuwait_first_client_foundation.py`, hire hook, `doc_type_map` / onboarding label patches, matrix harness.  
3. Confirm `WATHEFNI_CIVIL_ID_KEY` on staging.  
4. Boot service → `ensure_foundation_schema` via schema ensure.  
5. Seed **one** default legal entity per pilot tenant (EN + AR names, CR/licence/PAM text).  
6. Run local-style foundation matrix against staging isolation schemas.  
7. Run **frozen** Offers/Hiring + post-hire regression matrices (dry_run delivery).  
8. Manual UI checks: Civil ID mask/reveal RBAC; Arabic PDF RTL render; national vs expat checklists.  
9. Owner sign-off → only then plan production promote (separate instruction).  

**Rollback:** restore pre-staging code pin; foundation tables are additive — drop only throwaway qual schemas; production tenants must not receive schema until promote.

---

## Explicit non-goals (still out of scope)

- Automatic legal compliance claims  
- Leave-law enforcement  
- EOS / PIFSS calculations  
- Fine calculations  
- Statutory overtime multipliers  
- Payroll payments  
- PAM / MOI / PACI filings or API verification  
- Destructive merge of historical `residency_iqama` rows  
- Deploy to staging or production in this step  

---

## Stop condition

Local remediation report complete. **Stop after this report. Do not deploy.**
