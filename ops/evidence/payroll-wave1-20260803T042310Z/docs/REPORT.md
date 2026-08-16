# Payroll Wave 1 — Foundation REPORT

**Stamp:** `20260803T042310Z`  
**Evidence:** `ops/evidence/payroll-wave1-20260803T042310Z/`  
**Scope:** local/staging only. No production deploy. No money authority.

## Gate summary

| Gate | Verdict |
|---|---|
| Staging foundation qualify | **GO** — `STAGING_PAYROLL_WAVE1_FOUNDATION_GO` |
| Money / payment_processing | **NO-GO** (hard disabled) |
| Production deploy | **NO-GO** (not attempted) |
| Production synthetic canary | **NO-GO** until prod migrate + quarantine + synthetic qualify path exist (see blockers) |

## What shipped

### Models / schema (`ops/sql/payroll_authority_wave1_v1.sql`)

- `payroll_company_settings` — mode `native|external|parallel_shadow`, `payment_processing='disabled'` CHECK, attendance input source, Art.70 = **6** months
- `payroll_compensation_contracts` + `payroll_compensation_components` + `payroll_compensation_events` — effective-dated, draft/approved/superseded/cancelled, row_version
- `payroll_periods` + `payroll_period_events` — open → locked → closed → reopen
- `payroll_timesheets.quarantine_status`, `row_version`

### Module (`payroll_authority_wave1.py` v1.0.0)

- Company mode setter (all three modes)
- Contract draft / approve / replace; offer seeds **draft only**
- Overlap ban on approved contracts; creator + subject self-approval bans
- Period lifecycle with audit reason + concurrency
- Attendance source mix fail-closed (`legacy_records` XOR `approved_snapshots`)
- `PayrollInputExport@1.0.0` / `PayrollResultImport@1.0.0` schema stubs (no money authority)
- Soft quarantine for May 2026 smoke timesheets (IDs known from Wave 0)

### Permissions / SOD

- New `payroll.approve` permission
- `payroll_operator`: read + manage + approve (**no** export)
- Team manager: read + manage + approve (**no** export)
- Owner/HR retain export; SOD pair is `payroll.approve` × `payroll.export`
- Tool map: `approve_timesheet` / `reject_timesheet` → `payroll.approve`
- Wave1-gated `decide_timesheets`: reason, concurrency, self/creator ban, manager scope, quarantine block

### Scripts

- `wathefni-orchestrator/ops/migrate-payroll-authority-wave1.sh` (refuses production / `wathefni`)
- `wathefni-orchestrator/smoke-test-payroll-authority-wave1.py`
- `ops/qualify-payroll-authority-wave1-staging.sh`

## Staging proof (all green)

Evidence remote + tests under `ops/evidence/payroll-wave1-20260803T042310Z/`.

| Proof | Result |
|---|---|
| Migrate schema + settings | MIGRATE_OK; 6 tables; timesheet cols present |
| Smoke quarantine | **2** rows quarantined; `hard_deleted=false` |
| Contract draft → approve → replace | PASS |
| Creator / subject self-approve denial | PASS |
| Overlapping approved denial | PASS |
| Modes native / external / parallel_shadow | PASS |
| Period open → lock → close → reopen | PASS |
| SOD + payroll_operator lacks export | PASS |
| Manager has approve, lacks export | PASS |
| Input-source mix enforcement | PASS |
| Adapter schema validation | PASS |
| Offer seeds draft only | PASS |
| Honesty: payment_processing=disabled | PASS |
| Sibling freezes (E360 / Onboarding / Attendance / Leave / Shifts) | all green |

Smoke: **51 passed, 0 failed**. Roles smoke: ALL PASSED.

## Honesty invariants (always)

```
payment_processing = disabled
money_authority = false
gross_to_net / pifss / bank_wps / eos_auto / payslips_as_money / journals / xbrl = false
annual_leave_eligibility_months = 6
```

## Blockers for production synthetic canary

1. **No prod migrate path** — staging script intentionally refuses `wathefni`; need a dedicated `migrate-payroll-authority-wave1-prod.sh` with ACK + synthetic-only markers (pattern: Leave Wave 1B).
2. **Prod quarantine not applied** — May smoke rows were quarantined on **staging** only; production still has the two draft smoke timesheets until a controlled quarantine run.
3. **Wave1 flag not enabled on prod** — `WATHEFNI_PAYROLL_WAVE1` + `SYNTHETIC_ONLY=1` + marker/prefix allowlists must be explicit; default-on is forbidden.
4. **No prod-synthetic qualify script** — need evidence pack proving only `PYW1` / `965539*` subjects touched, sibling freezes green, money still off.
5. **Owner dual capability** — owners still hold approve+export (expected); custom-role SOD warnings only. Acceptable for canary if export stays unused and payment disabled.
6. **Counsel / bank / vendor items from Wave 0B** — do **not** block foundation synthetic canary; they block later money / WPS / EOS waves.

## Production synthetic canary — GO/NO-GO

**NO-GO now** for executing a production synthetic canary.

**Ready to design next:** a Wave 1B prod-synthetic canary that only:

- migrates schema with refuse-unless-ACK
- enables Wave1 for WATHEFNI with `SYNTHETIC_ONLY=1`
- quarantines the two May smoke rows
- exercises contract/period/mode/SOD against `PYW1` markers only
- keeps `payment_processing=disabled` and never calls export as money

**Hard NO-GO forever in this wave:** real money, G2N, PIFSS, bank/WPS, EOS, payslips-as-money, journals, XBRL, broad real-employee payroll authority.

## Follow-ups (not in this gate)

- Dashboard surfaces for contracts/periods/modes
- Action-registry tools for contract/period APIs
- Persist Wave1 env on staging systemd drop-in (smoke set env inline)
- Wave 1B prod-synthetic qualify + quarantine
