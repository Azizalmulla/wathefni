# Policy-pack contract (Wave 3H)

Required fields on every pack version:

- pack_code
- jurisdiction_code
- worker_category
- policy_version
- effective_from / effective_to
- status (verified|reserved|deprecated|draft)
- enabled
- source_refs[]
- content_hash (immutable identity)
- required_employment_fields
- contract_types / pay_frequencies / probation_statuses
- notice_rules
- probation_rules
- fixed_term_rules
- termination_case_classes / exceptional_case_classes
- exceptional_case_escalation
- settlement_ownership
- service_certificate
- retention
- allowed_lifecycle_actions
- disabled_fallbacks
- mandatory_rules
- ui_copy / disclaimer

Tenant overrides may only tighten (raise floors / keep safe booleans). Immutable statutory keys cannot be overridden.
