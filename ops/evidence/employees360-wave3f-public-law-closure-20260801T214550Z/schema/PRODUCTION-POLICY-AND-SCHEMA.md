# Final production policy values — Wave 3F

```json
{
  "tier": "small",
  "timezone": "Asia/Kuwait",
  "show_notice_hints": false,
  "notice_hint_monthly_days": 90,
  "notice_hint_other_days": 30,
  "require_last_working_day": true,
  "require_employment_classification": true,
  "require_termination_case_class": true,
  "allow_reinstate_after_effective": false,
  "jurisdiction_mode": "kuwait_private_sector_only",
  "document_retention_mode": "retain",
  "document_retention_floor_days": 365,
  "auto_cancel_shifts": false,
  "auto_decline_leave": false,
  "monetary_calculations_owner": "payroll",
  "settlement_packet_mode": "inputs_only",
  "service_certificate_default": true,
  "exceptional_cases_manual_only": true,
  "revoke_mode": "end_of_last_working_day",
  "effective_time_mode": "start_of_effective_date",
  "downstream_mode": "warn_first",
  "require_impact_ack": true,
  "require_counsel_gate": false,
  "allow_self_approval": false,
  "rehire_same_employee_key": true,
  "scheduler_cadence": "hourly",
  "lag_alert_seconds": 7200,
  "wave": "wave3f"
}
```

## Required termination payload fields
- `contract_type`: `unlimited` | `fixed_term`
- `pay_frequency`: `monthly` | `other`
- `probation_status`: `none` | `active` | `completed`
- `probation_start_date` + `probation_end_date` when `probation_status=active`
- `termination_case_class`: see vocabulary in module
- `termination_effective_on` + `last_working_day`
- `exceptional_escalation_note` when case is exceptional

## Schema changes
- `employee_employments`: `contract_type`, `pay_frequency`, `probation_status`, `probation_start_date`, `probation_end_date`
- `employee_lifecycle_service_certificates` table
- Settlement packet enriched with classification + retention floor; still **no amounts**
- Schema version: `employees360-wave3f-public-law-closure-v1`

## Migration impact on existing employee records
- Existing employments may have **NULL** classification columns.
- Termination create **fails closed** with `manual_review_missing_classification` until HR supplies fields — **no inference**.
- Prior `require_counsel_gate=true` DB rows migrate to Wave 3F via `_normalize_policy` (counsel gate off for normal public-law ops; PL1–PL10 checklist remains recordable).
- Historical settlement packets unchanged; new terminations get Wave 3F packet shape.
