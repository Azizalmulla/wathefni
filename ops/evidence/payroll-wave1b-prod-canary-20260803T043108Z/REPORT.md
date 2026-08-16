# Payroll Wave 1B — production synthetic qualification

**Stamp:** `20260803T043108Z`  
**Evidence:** `ops/evidence/payroll-wave1b-prod-canary-20260803T043108Z/`  
**Module:** `payroll_authority_wave1.py` **v1.0.0**  
**Mode:** production WATHEFNI · **SYNTHETIC_ONLY** · markers **PYW1** / **965539***  

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Payroll Wave 1 foundation | **GO** |
| Freeze Payroll Wave 1 foundation | **GO** (see blockers) |
| Real compensation / money authority | **NO-GO** |
| Wave 2 (external adapter / native preview) | **NO-GO / not started** |

---

## Migration

```
wave1_version 1.0.0
honesty_ok {'payment_processing': 'disabled', 'money_authority': False, 'annual_leave_eligibility_months': 6}
connected_db wathefni
tables ['payroll_company_settings', 'payroll_compensation_components', 'payroll_compensation_contracts', 'payroll_compensation_events', 'payroll_period_events', 'payroll_periods']
timesheet_cols ['quarantine_status', 'row_version']
smoke_before [{'timesheet_id': '7950dafd-6cf7-44b1-9f92-26f685c34ab5', 'employee_key': 'WATHEFNI-96597727743', 'status': 'draft', 'quarantine_status': 'wave0_smoke_quarantined', 'payroll_status': 'quarantined'}, {'timesheet_id': 'cc68a9fb-df72-4e13-a0db-cc13a3805380', 'employee_key': 'WATHEFNI-96566363363', 'status': 'draft', 'quarantine_status': 'wave0_smoke_quarantined', 'payroll_status': 'quarantined'}]
quarantine {'ok': True, 'count': 2, 'hard_deleted': False}
smoke_after [{'timesheet_id': '7950dafd-6cf7-44b1-9f92-26f685c34ab5', 'employee_key': 'WATHEFNI-96597727743', 'status': 'draft', 'quarantine_status': 'wave0_smoke_quarantined', 'payroll_status': 'quarantined'}, {'timesheet_id': 'cc68a9fb-df72-4e13-a0db-cc13a3805380', 'employee_key': 'WATHEFNI-96566363363', 'status': 'draft', 'quarantine_status': 'wave0_smoke_quarantined', 'payroll_status': 'quarantined'}]
MIGRATE_OK payroll_authority_wave1_prod
```

---

## Quarantine (May 2026 smoke — soft, no delete)

```json
{
  "quarantined": [
    {
      "timesheet_id": "7950dafd-6cf7-44b1-9f92-26f685c34ab5",
      "employee_key": "WATHEFNI-96597727743",
      "status": "draft",
      "payroll_status": "quarantined",
      "quarantine_status": "wave0_smoke_quarantined"
    },
    {
      "timesheet_id": "cc68a9fb-df72-4e13-a0db-cc13a3805380",
      "employee_key": "WATHEFNI-96566363363",
      "status": "draft",
      "payroll_status": "quarantined",
      "quarantine_status": "wave0_smoke_quarantined"
    }
  ],
  "hard_deleted": false,
  "count": 2
}
```

Smoke IDs:
- `cc68a9fb-df72-4e13-a0db-cc13a3805380`
- `7950dafd-6cf7-44b1-9f92-26f685c34ab5`

Quarantine survived rollback: **YES**

---

## Production flags (after deploy)

```
=== SHAs after ===
57f216307e43e0b91c3fd9d54773fb084795244fc31a6bc15b2c3b23ce55bd89  /opt/wathefni/orchestrator/app.py
7a49696446deb6e469a8a4b23e615932b8c849d28f521cbcb3ccc9c49ffd0207  /opt/wathefni/orchestrator/payroll_authority_wave1.py
68e96706d3cfb4e4eef43893b2a537ca233d9980cc60c709efc515520502fb80  /opt/wathefni/orchestrator/tenant_control_roles.py
3416837273e526fff8d23eeccddb2dd10870eb7e779b691225c8a4607863d358  /opt/wathefni/orchestrator/tool_call_orchestrator.py
=== flags after ===
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
WATHEFNI_LEAVE_AUTHORITY=on
WATHEFNI_PAYROLL_WAVE1=1
WATHEFNI_PAYROLL_WAVE1_COMPANIES=WATHEFNI
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS=PYW1,PYW1-SYNTH|
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY=1
WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_PHONE_PREFIXES=965539
WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
```

Required:
- `WATHEFNI_PAYROLL_WAVE1=1`
- `WATHEFNI_PAYROLL_WAVE1_COMPANIES=WATHEFNI`
- `WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_ONLY=1`
- `WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_KEY_MARKERS=PYW1,PYW1-SYNTH|`
- `WATHEFNI_PAYROLL_WAVE1_SYNTHETIC_PHONE_PREFIXES=965539`
- `payment_processing=disabled` (honesty + DB CHECK)

---

## Backup / rollback

- Backup: `/opt/wathefni/backups/production-pre-payroll-wave1b-20260803T043108Z`
- Rollback executed + verified: **YES**
- Redeploy after rollback completed; canary re-run

---

## Synthetic canary counts

| Pass | Passed | Failed |
|---|---:|---:|
| Before rollback | 37 | 0 |
| After redeploy | 37 | 0 |
| Residual synthetic | 0 | |

---

## Sibling freezes

| Suite | Result |
|---|---|
| Employees 360 (local) | 57/0 |
| Onboarding (local) | 54/0 |
| Attendance (local) | 26/0 |
| Leave (local) | 35/0 |
| Shifts (local) | 96/0 |
| Production freezes | PASS |

---

## Blockers

- None for synthetic foundation freeze scope.

Money, G2N, PIFSS, WPS/bank, EOS, payslips-as-money, journals, XBRL, and Wave 2 remain **NO-GO**.
