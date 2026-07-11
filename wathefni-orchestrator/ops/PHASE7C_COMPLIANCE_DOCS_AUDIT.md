# Phase 7C — Compliance documents reconciliation audit

**Mode:** read-only measurement. No backfill, no write-path, no production mutation.

## Source-of-truth model

| Store | Role |
|-------|------|
| `file_registry` | Binary / file identity (`file_id`, sha256, storage) |
| `onboarding_items` | Workflow / checklist state (`pending` / `received` / …) |
| `employee_documents` | Durable employee document receipt + metadata spine |
| `compliance_documents` | Expiry / renewal / compliance alert surface |

## Type map (audit authority)

### Onboarding document `item_id` (default Kuwait)

| item_id | Notes |
|---------|--------|
| `civil_id` | Required; compliance-synced on upload |
| `passport` | Optional; compliance-synced on upload |
| `personal_photo` | Required; receipt only (not compliance) |
| `residency_iqama` | Optional; **not** the same key as compliance `residency` |
| `work_permit` | Optional; compliance UI type exists; upload dual-write allowlist does **not** include it today |
| `employment_contract` | Required; receipt only |
| `offer_letter` | Optional; receipt only |

Related soft expiry **tasks** (workflow UX, not compliance authority):
`civil_id_expiry`, `passport_expiry`, `residency_expiry`, `work_permit_expiry`.

### `employee_documents.document_type`

Set from onboarding item `document_type` or falls back to `item_id` in `record_employee_document_receipt`.

### `compliance_documents.document_type` (canonical UI / seed)

| document_type | Label |
|---------------|--------|
| `civil_id` | Civil ID |
| `passport` | Passport |
| `residency` | Residency (Iqama) |
| `work_permit` | Work Permit |
| `medical` | Medical Document |
| `education_cert` | Education Certificate |

Default seed types: `civil_id`, `passport`, `work_permit`.

### Upload dual-write allowlist (current code)

Only these employee document types update `compliance_documents` on receipt:

`civil_id`, `passport`, `medical`, `education_cert`

### Ambiguous / alias families (flag, do not auto-merge)

| Family | Keys |
|--------|------|
| medical | `medical`, `medical_check` |
| residency | `residency`, `residency_iqama` |
| education | `education_cert`, `education`, `certificate` |

## Script

```bash
WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env \
  python3 ops/staging-phase7c-compliance-docs-audit.py \
  --company WATHEFNI \
  --json-out /tmp/p7c-wathefni.json \
  --md-out /tmp/p7c-wathefni.md
```

Guardrails:

- `--company` required
- refuses `ALL` / `*` unless `--allow-unsafe-all-companies` (still unimplemented — forces single company)
- `SET SESSION CHARACTERISTICS` / `readonly=True` + verifies `transaction_read_only`
- samples are hashed (`emp_<sha256[:12]>`) — no phones/emails/URLs

## Proposed write rules (not implemented)

1. `file_registry` owns binary/file identity.
2. `onboarding_items` owns checklist state; never invent files.
3. `employee_documents` is the durable receipt spine.
4. `compliance_documents` derives from receipts for compliance-relevant types only.
5. Never create compliance rows without a receipt or explicit HR action.
6. Never overwrite a newer expiry with null/older extraction.
7. Reconciliation v1: upsert/link only — no historical deletes.
8. Keep an explicit `item_id` ↔ `document_type` ↔ compliance type map; no silent alias merges.
9. Soft onboarding expiry tasks stay HR UX until a later approved sync from compliance.
10. Future writes: company-scoped, idempotent, dry-run first.

## Employee-app upload expansion

Do **not** expand broadly until measured file-link / tenant mismatch buckets are empty or explicitly accepted, and a write-path reconciliation plan is approved. Keep behind `WATHEFNI_EMPLOYEE_APP=off` until then.
