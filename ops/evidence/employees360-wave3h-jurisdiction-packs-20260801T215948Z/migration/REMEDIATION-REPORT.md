# Migration / remediation report — Wave 3H

## Policy
- Never silently classify uncertain records.
- Eligible path: explicit `jurisdiction_code=KW` + `worker_category=private_sector` → bind `KW_PRIVATE_SECTOR` `1.0.0`.
- Missing or conflicting fields → `employee_policy_pack_remediation` (`status=open`) + `policy_pack_status=remediation`.

## Staging WATHEFNI run
- Idempotency key: `wave3h-migrate-20260801T215948Z-final`
- Result: `remediation=10`, `resolved=0`, `total=10`
- Interpretation: existing employments lacked authoritative jurisdiction/category columns → correctly queued for HR confirmation.

## Lifecycle path (preserves Wave 3F for verified KW)
When termination payload includes:
```json
{"jurisdiction_code":"KW","worker_category":"private_sector", ...classification...}
```
the employment is bound to `KW_PRIVATE_SECTOR` and Wave 3F rules apply via the pack overlay.

## Confirmation API
`confirm_employment_kw_private_sector(legacy, company_code=..., employment_id=...)`  
Explicit HR confirmation closes open remediation rows and binds the verified pack.
