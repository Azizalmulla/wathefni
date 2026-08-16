# Employee Migration & Sync — Field Model (3 layers)

Supersedes the thin “canonical-only” sketch in earlier expansion notes for
**mapping / deep records**. P1 production-safe foundation path remains mandatory.

Contract (P2): `employee_migration_sync_p2_field_model` @ `2.0.0`  
Company canary: `WATHEFNI` only (same foundation allowlist).

---

## Why three layers

| Layer | Purpose | May hold Bank / Civil ID / lifecycle? |
|---|---|---|
| **1. Canonical Wathefni fields** | Fields Wathefni owns operationally | **Yes — only here**, with domain authority |
| **2. Company custom fields** | Structured company-specific attributes Wathefni does not natively own | **No** for bank, identity, compliance, leave, lifecycle |
| **3. Raw source payload / provenance** | Original source headers/values for every row | Always retain; never silently discard |

Custom fields are **not** a dumping ground for concepts that need Wathefni business logic.

---

## Layer 1 — Canonical field registry

Code registry (not free-form DB keys). Each entry declares:

- `field_key`, labels EN/AR, value type
- `domain` (roster | identity | contacts | employment | bank | documents | compliance)
- `write_target` (hub employees, assignment history, `employee_identity`, ESS personal, Bank ESS proposed, document metadata, …)
- `authority_class`: `roster_safe` | `imported_non_authoritative` | `needs_review_if_conflict` | `bank_proposed_only` | `lifecycle_review_only`
- `sensitivity`: `public` | `pii` | `sensitive_id` | `bank`
- `conflict_policy`: skip | review | never_overwrite_confirmed

### P2 canonical set

| field_key | Domain | Authority |
|---|---|---|
| `name`, `phone`, `email`, `position_title`, `department`, `start_date`, `manager_phone` | roster | existing P1 rules (material name → review) |
| `external_employee_id`, `payroll_id`, `source_system` | roster/match | mapping + source_mappings |
| `civil_id`, `passport_number`, `nationality` | identity | **imported / staged**; never set `*_confirmed=true`; conflict with confirmed → Needs review |
| `employee_category` | identity | write via foundation APIs when empty/compatible; else review |
| `address_line1`, `address_line2`, `city`, `governorate`, `country`, `postal_code` | contacts | ESS personal `profile_json` overlay as **imported** provenance |
| `emergency_contact_name`, `emergency_contact_phone`, `emergency_contact_relation` | contacts | ESS `emergency_json` imported overlay |
| `employment_status` | employment | informational stamp / review; **never hard-deactivate** (P6) |
| `bank_iban`, `bank_name`, `bank_account_holder`, `bank_swift`, `bank_account_number` | bank | **Bank ESS proposed-only** staging; never verified / payroll-effective |
| `document_type`, `document_expiry`, `document_issue_date`, `document_number` | documents | `employee_document_metadata` with `verification_status=unverified` |
| `compliance_doc_type`, `compliance_status`, `compliance_expiry` | compliance | evidence/status import with provenance; **no auto-seed** of missing campaign docs |

Missing source value = **not supplied** (do not write empty/false).

---

## Layer 2 — Company custom fields

```sql
employee_custom_field_definitions (
  field_id uuid PK,
  company_code text NOT NULL,
  field_key text NOT NULL,          -- slug, unique per company
  label_en text NOT NULL,
  label_ar text,
  value_type text NOT NULL,         -- text|number|date|boolean|enum
  enum_values jsonb NOT NULL DEFAULT '[]',
  description text,
  active boolean NOT NULL DEFAULT true,
  created_by text,
  created_at timestamptz, updated_at timestamptz,
  UNIQUE (company_code, field_key),
  CHECK (field_key ~ '^[a-z][a-z0-9_]{0,63}$'),
  -- hard block reserved canonical keys at write time in app code
)

employee_custom_field_values (
  company_code text NOT NULL,
  employee_key text NOT NULL,
  field_id uuid NOT NULL REFERENCES employee_custom_field_definitions(field_id),
  value_text text,                  -- normalized display/search
  value_json jsonb,                 -- typed value
  authority text NOT NULL DEFAULT 'imported',
  source_system text,
  source_batch_id uuid,
  source_row_id uuid,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, employee_key, field_id)
)
```

**Reserved:** any canonical `field_key` (and bank/identity synonyms) cannot be created as custom.

Examples allowed: cost_center, grade, employee_category_code (vendor), business_unit, location_code.

---

## Layer 3 — Raw source payload

Never drop unknown columns at parse time.

```sql
employee_import_source_payloads (
  payload_id uuid PK,
  company_code text NOT NULL,
  batch_id uuid NOT NULL REFERENCES employee_import_batches(batch_id) ON DELETE CASCADE,
  row_id uuid REFERENCES employee_import_rows(row_id) ON DELETE SET NULL,
  row_number integer NOT NULL,
  source_system text,
  external_employee_id text,
  headers jsonb NOT NULL,           -- ordered original header strings
  values jsonb NOT NULL,            -- {original_header: original_cell_as_text}
  received_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (batch_id, row_number)
)
```

Also: `employee_import_rows.source_payload jsonb` (denormalized copy for UI) via `ALTER … ADD COLUMN IF NOT EXISTS`.

P1 `raw` / `normalized` stay **alias-normalized known fields** for backward compatibility. Source-only data lives in layer 3.

---

## Reusable mapping profiles

```sql
employee_import_mapping_profiles (
  profile_id uuid PK,
  company_code text NOT NULL,
  source_system text NOT NULL,      -- e.g. csv:workday_export, sftp:oracle
  name text,
  status text NOT NULL DEFAULT 'draft',  -- draft|active|archived
  version integer NOT NULL DEFAULT 1,
  mappings jsonb NOT NULL,          -- array of MappingRule
  unmapped_policy text NOT NULL DEFAULT 'retain_source_only',
  created_by text,
  created_at timestamptz,
  updated_at timestamptz,
  confirmed_at timestamptz,
  UNIQUE (company_code, source_system, version)
)

-- One active profile per (company, source_system):
CREATE UNIQUE INDEX … ON (…) WHERE status = 'active';
```

### MappingRule

```json
{
  "source_header": "Cost Center",
  "source_header_normalized": "cost_center",
  "disposition": "canonical|custom|create_custom|source_only|ignore",
  "canonical_field": "department|null",
  "custom_field_key": "cost_center|null",
  "custom_field_label_en": "Cost center",
  "custom_field_label_ar": null,
  "custom_value_type": "text",
  "suggested": true,
  "suggestion_confidence": 0.96,
  "confirmed": false
}
```

### Disposition semantics

| Disposition | Batch behavior |
|---|---|
| `canonical` | Apply via domain writer + authority rules |
| `custom` | Write `employee_custom_field_values` |
| `create_custom` | Create definition (if allowed) then write value |
| `source_only` | Retain in payload only; operationally ignored |
| `ignore` | Retain in payload; mark intentionally unused |

**Unmapped** columns default to `source_only` (retain). They **do not** fail the batch.

Auto-suggest when confidence is high (alias / exact / normalized match). Ambiguous suggestions stay unconfirmed — HR must review. Never silently map ambiguous fields.

Batch stores `mapping_profile_id` + `mapping_snapshot` jsonb at preview/confirm time.

---

## Preview / UX flow

1. Upload file (+ optional source_system)
2. **Map fields** — every source column → one disposition; show Unmapped; save profile
3. Preview row outcomes (create/update/skip/review) using confirmed mapping
4. Confirm → apply (idempotent)
5. Needs review / History / exception CSV / rollback unchanged in spirit

---

## Apply + authority (P2)

```
For each mapped value on commit:
  if missing/blank → skip (not supplied)
  if canonical:
    run domain writer with conflict_policy
    on conflict with higher authority → row/field Needs review (no silent overwrite)
  if custom / create_custom:
    upsert definition (blocked if reserved) + value authority=imported
  always:
    persist full source payload (layer 3)
```

### Bank

- Map only to canonical bank_* fields
- Stage as **proposed / imported** (masked in HR lists)
- Never write `employee_bank_verified` or `employee_bank_effective`
- Never send invites/messages

### Identity

- Stage sensitive IDs in `employee_identity.ocr_pending` with `source=migration_import` (non-authoritative)
- Do **not** set `civil_id_confirmed` / passport confirmed
- If already confirmed and value differs → Needs review

### Documents / compliance

- Metadata / evidence with `unverified` + provenance
- No compliance campaign seed; no onboarding start; no invites

### Rollback

Extend foundation rollback to:

- deactivate custom values written by batch (`source_batch_id`)
- clear migration-staged identity pending entries stamped with batch_id
- clear migration bank staging for batch
- remove unverified document_metadata created by batch  
Hub employee create rollback remains as P1.

---

## Migration risks vs existing P1 schema

| Risk | Mitigation |
|---|---|
| P1 parser **drops unknown headers** | New parse path retains `headers`+`values`; keep `raw` alias-normalized for compat |
| `CREATE TABLE IF NOT EXISTS` only — no ALTERs | Explicit `ALTER … ADD COLUMN IF NOT EXISTS` for `source_payload`, `mapping_profile_id`, `mapping_snapshot` |
| Dual storage drift (`raw`/`normalized`/hub) | Layer 3 is source of truth for originals; writers own canonical targets |
| `CONTRACT_VERSION` inside idempotency key | P2 bump ⇒ same file gets new batch id (documented); old P1 batches remain readable |
| Overwriting verified identity/bank | Authority gates + Needs review; bank proposed-only |
| Custom fields used for Civil ID/bank | Reserved-key blocklist + disposition validation |
| Rollback incomplete for child tables | Batch-stamped deletes/clears in rollback path |
| Auto-map wrong columns | Suggestions require `confirmed=true` before apply (except exact high-confidence prefill still editable) |
| Attendance `attendance_import_mappings` confusion | Separate tables/names; do not reuse |

---

## Out of scope (still deferred)

- P3 onboarding migration states
- P4 leave/payroll/shift opening balances ledgers
- P5 live API/SFTP connectors (profiles are designed for reuse)
- P6 leaver hard-deactivate automation
- Auth Wave 2 Phase 6
