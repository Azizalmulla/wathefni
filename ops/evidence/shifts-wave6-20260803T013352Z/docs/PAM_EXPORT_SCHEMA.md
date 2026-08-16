# PAM export contract `pam-export@1.0.0`

## Status
Always `manual_submission_required`. `submission: false`. No government API.

## Payload fields
- contract_version, company_code
- period {period_id, name, start_date, end_date, timezone, site_key, branch_key}
- version {version_id, version_no, fingerprint, published_at}
- declared_daily_working_periods[] (employee, date, start/end, ends_next_day, break_minutes=null unless present, site/branch/role, schedule provenance, optional rotation_assignment_id)
- weekly_rest_days {employee_key: [dates]}
- holidays[]
- payroll_money: false

## Fingerprint
SHA-256 over canonical JSON payload (sort_keys).

## Sample CSV (EN)
```csv
employee_key,employee_name,date,start_time,end_time,ends_next_day,site_key,branch_key,role,version_id
"WATHEFNI-SHW6-EXAMPLE","SHW6-SYNTH| Emp","2026-08-10","09:00:00","17:00:00","False","SITE-A","","ops","00000000-0000-0000-0000-000000000001"
```

## Sample CSV (AR headers)
```csv
رمز_الموظف,اسم_الموظف,التاريخ,بداية,نهاية,يمتد_لليوم_التالي,الموقع,الفرع,الدور,الإصدار
"WATHEFNI-SHW6-EXAMPLE","SHW6-SYNTH| Emp","2026-08-10","09:00:00","17:00:00","False","SITE-A","","ops","00000000-0000-0000-0000-000000000001"
```

## Unsupported / manual notes
- no_government_submission
- manual_submission_required
- breaks_not_inferred
