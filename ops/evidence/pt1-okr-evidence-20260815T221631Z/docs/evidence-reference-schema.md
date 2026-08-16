# Evidence-reference schema

Table: `talent_evidence_refs`  
Unique: `(company_code, source_authority, source_id, source_version, employee_key)`

| Field | Role |
|---|---|
| company_code / employee_key | Tenant + person |
| source_module / source_authority / source_id / source_version | Pointer to canonical object |
| as_of | Effective time |
| evidence_kind | Kind |
| provenance_class | Provenance |
| consume_contract | Admission |
| payload_hash | Integrity marker (not a copied rating) |
| permission_class | Source permission intersection |
| claimed_not_verified | Claimed skill guard |
| classification_input_eligible | Forced false for AI-SYNTHESIZED and claimed skills |
| retired_at / inaccessible / source_module_disabled | Lifecycle |

Default: pointer / read-through.  
Constraint: `metadata.copied_canonical_rating` must be null.  
Idempotent indexing via ON CONFLICT on the unique key.
