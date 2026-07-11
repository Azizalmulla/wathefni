# Phase 7C compliance docs audit — WATHEFNI

- read_only: `True`
- no_writes: `True`
- total_mismatch_events: **6**

## Store counts

- `employees`: 3
- `onboarding_items`: 18
- `onboarding_document_like`: 15
- `employee_documents`: 4
- `compliance_documents`: 15
- `file_registry_employee_docs`: 4

## Mismatch counts

- `received_without_employee_doc`: 0
- `employee_doc_without_received_item`: 2
- `employee_doc_without_file`: 0
- `orphan_employee_files`: 0
- `compliance_missing_for_synced_received`: 0
- `compliance_without_employee_doc`: 2
- `expiry_status_conflicts`: 1
- `null_expiry_on_received_compliance`: 1
- `duplicate_employee_docs`: 0
- `duplicate_compliance_docs`: 0
- `ambiguous_type_mappings`: 0
- `orphan_employee_keys`: 0
- `company_mismatch`: 0

## Samples (redacted)

### employee_doc_without_received_item
- `{"document_type": "civil_id", "onboarding_status": "pending", "reason": "onboarding_not_received", "sample_id": "emp_2c08123fca34"}`
- `{"document_type": "bank_details", "onboarding_status": "pending", "reason": "onboarding_not_received", "sample_id": "emp_2c08123fca34"}`

### compliance_without_employee_doc
- `{"compliance_status": "received", "document_type": "medical", "sample_id": "emp_2c08123fca34"}`
- `{"compliance_status": "valid", "document_type": "passport", "sample_id": "emp_2c08123fca34"}`

### expiry_status_conflicts
- `{"document_type": "civil_id", "kind": "expiry_date_mismatch", "sample_id": "emp_2c08123fca34"}`

### null_expiry_on_received_compliance
- `{"compliance_status": "received", "document_type": "medical", "sample_id": "emp_2c08123fca34"}`

## Proposed write rules (not implemented)

- file_registry is the authority for binary/file identity (file_id, sha256, storage).
- onboarding_items remains workflow authority (pending/received/waived) and must not invent files.
- employee_documents is the durable receipt/metadata spine linking item_id/document_type to storage/extraction.
- compliance_documents is the expiry/renewal alert surface; derive from employee_documents for compliance-relevant types only.
- Never create compliance rows without a receipt or explicit HR action.
- Never overwrite a newer expiry with null/older extraction values.
- Never delete historical rows in reconciliation v1 — upsert/link only.
- Maintain an explicit item_id ↔ document_type ↔ compliance_type map; do not silently alias residency_iqama↔residency or medical_check↔medical without operator-visible migration.
- Keep onboarding soft expiry tasks as HR UX until a later sync from compliance_documents.
- All future write paths must be company-scoped, idempotent, and dry-run first.

## Employee-app upload readiness recommendation

**Conditionally safe for a closed pilot** if uploads stay on the existing receipt pipeline (file_registry + employee_documents + onboarding item update) and compliance dual-write gaps are accepted as known. Do not enable broad production employee-app upload until a write-path reconciliation plan is approved.

