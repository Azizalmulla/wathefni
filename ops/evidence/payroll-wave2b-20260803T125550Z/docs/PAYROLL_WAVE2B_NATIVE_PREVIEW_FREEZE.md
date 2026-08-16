# Payroll Wave 2B — Native Preview Engine Freeze (Staging)

**Gate:** `STAGING_PAYROLL_WAVE2B_NATIVE_PREVIEW_GO`  
**Evidence:** `ops/evidence/payroll-wave2b-20260803T125550Z/`  
**Freeze:** **GO** for staging native preview only

## Production synthetic

**NO-GO** — requires a separate Wave 2B-B production synthetic path (not started).

## Frozen posture

- Deterministic preview engine only (`payroll_preview_policy@1.0.0`); **no AI calculations**
- Previews are **non-authoritative**; `payment_processing=disabled`
- Staging flags: `WATHEFNI_PAYROLL_WAVE2B=1`, `SYNTHETIC_ONLY=1`, markers `PYW2B`/`PYW1`, phones `965541*`/`965539*`
- New tables only (`payroll_preview_*`); Wave 1 / Wave 2A DDL and external flows untouched
- No bank files, WPS, remittance, journals, payslips, or payment execution

## Proven on staging

- Full-month salary; mid-month join/exit calendar-day proration
- Approved unpaid-leave deductions; fixed allowance + deduction; one-time adjustments
- Missing / overlapping contract fail-closed
- Idempotent calculation; recalculation after input change supersedes prior **successful** runs only
- KWD 3dp `ROUND_HALF_UP`; calculation fingerprints + audit events
- Counsel-gated items blocked as `review_only` / unsupported: PIFSS, OT premiums, sick-leave fractions, EOS, public-holiday/rest-day pay
- External mode blocks native preview; real employees refused under `SYNTHETIC_ONLY`
- Rollback green; Wave 2A external regression green; sibling freezes green

## Explicit NO-GO (outside this freeze)

- Production synthetic / production deploy of Wave 2B
- Payslips or any payment execution
- Authoritative G2N, PIFSS remittance, EOS, bank/WPS, journals
- Changes to frozen Wave 1 contracts or Wave 2A external adapter flows

## Rollback

Remove staging drop-in `zzzzzzzzzzzzzz-payroll-wave2b-preview.conf` and restart orchestrator-staging; preview tables may remain (non-authoritative). Wave 1 + Wave 2A retained.
