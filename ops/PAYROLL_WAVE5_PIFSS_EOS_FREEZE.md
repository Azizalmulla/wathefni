# Payroll Wave 5 — PIFSS & EOS Review Worksheets Freeze

**Gate:** `PROD_SYNTHETIC_PAYROLL_WAVE5_GO`  
**Evidence:** `ops/evidence/payroll-wave5b-prod-canary-20260803T144248Z/`  
**Staging evidence:** `ops/evidence/payroll-wave5-20260803T143036Z/`  
**Freeze:** **GO** for Wave 5 PIFSS + EOS **review worksheets** (synthetic-only production posture)

## Frozen posture

- Non-authoritative **PIFSS review worksheets** by employee category (Kuwaiti / GCC-national / expatriate)
- Non-authoritative **EOS / final-settlement review worksheets** (never automatic payable)
- Source/version provenance on rules and inputs; counsel-approved effective-dated rule tables
- Manual review → submit → approve; exception path with dual-control override + evidence
- Explicit `unsupported` / `counsel_required` / blocked Art. 51/53 and Law 17/2018 states
- `payment_processing=disabled`; no remittance, statutory filing, bank/WPS/AS’HAL, or AI
- No automatic legal-compliance claim; native results non-authoritative; external payroll remains authority
- Production flags: `WATHEFNI_PAYROLL_WAVE5=1`, `SYNTHETIC_ONLY=1`, markers `PYW5`/`PYW1`/`W5B`, phones `965541*`/`965540*`/`965539*`
- Additive tables only (`payroll_statutory_*`, `payroll_pifss_*`, `payroll_eos_*`)
- Wave 1 / 2A / 2B / 3 / 4 DDL and frozen flows untouched
- `SYNTHETIC_ONLY` refuses non-synthetic employee keys (actor phone alone cannot authorize)

## Proven on production synthetic

- Migrate/ACK `ACK_PRODUCTION_PAYROLL_W5B=YES`
- Canary ×2 (before rollback + after redeploy): **81/81** each, residual **0**
- Category separation; counsel-required / unsupported fail-closed
- Effective-dated counsel-approved rule-table versioning
- Dual-approval override with evidence; recalculation after source/rule changes
- Approved worksheet history retained (immutable payload; supersede on recalc)
- EN/AR + mobile UX smoke (local + prod)
- Rollback verified; Wave 1 + 2A + 2B + 3 + 4 retained; Wave 5 drop-in cleared then redeployed
- Sibling freezes green (E360 / Onboarding / Attendance / Leave / Shifts)
- Wave 1 / 2A / 2B / 3 / 4 freezes retained

## Explicit NO-GO (outside this freeze)

- Remittance, payments, or real statutory filing
- Bank / WPS / AS’HAL execution
- Treating worksheets as payable or compliance authority
- Changes to frozen Wave 1/2A/2B/3/4 contracts or flows
- Real-money pilot (see `ops/PAYROLL_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md`)

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-payroll-wave5b-*`  
(Removes Wave 5 drop-in + restores pre-5-B `app.py`/modules; Wave 1–4 drop-ins retained. Worksheet schema tables remain additive.)
