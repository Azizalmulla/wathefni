# Setup Console Phase 3A — Payroll Setup Completion

**Status:** PASS (canary qualified) · **Frozen**  
**Depends on:** Phase 2A payroll setup · Payroll Authority P1–P6 (calc/seal unchanged)  
**Do not auto-start:** next Setup Console phase · Employee App P1 · Auth Wave 2 Phase 6

## Verdict

**PASS** — canary live smoke **33/0**

Evidence: `ops/evidence/setup-console-phase3a-20260808T025752Z`  
Canary: `/opt/wathefni/ops/evidence/setup-console-phase3a-20260808T025752Z`

Smoke: `wathefni-orchestrator/smoke-test-setup-console-phase3a.py`

## Final Payroll Setup IA

```
Payroll (Setup Console)
├── Readiness (blockers + attention)
├── Wathefni-owned (rates / calc / sealing — read-only)
├── Required
│   ├── Mode (Wathefni | External)
│   ├── Cycle + cut-off
│   ├── Attendance → pay
│   ├── Working calendar (rest days + holiday pack/overrides)
│   ├── Statutory classifications gap panel (counts + Employees deep link)
│   ├── Company policy + compensation readiness
│   ├── Approvals / SOD
│   └── Authority level (Off / Preview / Allowlisted / Full) + confirm for full
├── Optional
│   └── Lateness / absence / unpaid leave money flags
└── Advanced
    ├── Enterprise SOD
    ├── Variance review thresholds (advisory)
    └── Authoritative allowlist search/add/revoke
```

## Ownership map

| Concern | Owner |
|---|---|
| Authority mode / cycle / attendance / working calendar / SOD / allowlist / variance | **Setup Console** |
| Statutory classification + PIFSS wage-base **facts** | Setup counts + **Employees** facts |
| Runs / preview / exceptions / approvals / finalize / payslips | **Payroll** |
| Statutory rates / formulas / versions / sealing rules | **Wathefni** |

No duplicate company-policy writers restored.

## Readiness matrix

| Profile | Calendar | Statutory gaps | Authority | Mode B |
|---|---|---|---|---|
| SME Wathefni | Required blocker until set | Attention until authoritative | Preview default via SME | — |
| Attendance-driven | Required | Attention | Preview → allowlisted | — |
| Shift-driven | Same calendar truth (no second calendar) | Attention | Preview | — |
| Enterprise SOD | Required | Attention→blocked when authoritative | Allowlisted/Full + confirm | — |
| Authoritative allowlist | Required | Blocked if incomplete while authoritative | Allowlist in Setup | — |
| Full authoritative | Required | Blocked if incomplete | Confirm + audit; history never rewritten | — |
| External Mode B | **Ignored** | **Ignored** | Forced off | Native controls hidden |

## Key additive surfaces

- `setup_console_payroll_phase3a.py`
- `payroll_employee_statutory_inputs` table (facts only; rate keys rejected)
- `setup_extras.weekend_days` / `calendar_configured`
- `public_holidays` company overrides + Wathefni fixed KW seed
- P6 `validate_payroll_readiness` additive calendar (+ statutory when authoritative)
- Setup allowlist candidates route

## Remaining Setup Console gaps

1. Roles/permissions Setup beyond Owner seed  
2. Leave / Attendance / Shifts / Docs / Compliance / Onboarding company-policy forms  
3. Parallel-shadow coexistence UX polish  
4. Richer employee statutory editor embedded in Setup (today gap counts + Employees deep link + API upsert)  
5. Cross-company payroll templates  
