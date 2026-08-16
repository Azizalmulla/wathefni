# Payroll Wave 5 — PIFSS & EOS Review Worksheets Freeze

**Gate:** `STAGING_PAYROLL_WAVE5_PIFSS_EOS_GO`  
**Evidence:** `ops/evidence/payroll-wave5-20260803T143036Z/`  
**Freeze:** **GO** for Wave 5 PIFSS + EOS **review worksheets** on **staging only**

**Production synthetic qualification:** **NO-GO** (requires Wave 5-B prod synthetic path; not started)

## Frozen posture

- Non-authoritative **PIFSS review worksheets** by employee category (Kuwaiti / GCC-national / expatriate)
- Non-authoritative **EOS / final-settlement review worksheets** (never automatic payable)
- Source/version provenance on rules and inputs; counsel-approved effective-dated rule tables
- Manual review → submit → approve; exception path with dual-control override + evidence
- Explicit `unsupported` / `counsel_required` / blocked Art. 51/53 and Law 17/2018 states
- `payment_processing=disabled`; no remittance, statutory filing, bank/WPS/AS’HAL, or AI
- No automatic legal-compliance claim; native results non-authoritative; external payroll remains authority
- Staging flags: `WATHEFNI_PAYROLL_WAVE5=1`, `SYNTHETIC_ONLY=1`, markers `PYW5`/`W5`, phones `965541*`/`965540*`/`965539*`
- Additive tables only (`payroll_statutory_*`, `payroll_pifss_*`, `payroll_eos_*`)
- Wave 1 / 2A / 2B / 3 / 4 DDL and frozen flows untouched

## Proven on staging

- Migrate + honesty asserts (`MIGRATE_OK`, `HONESTY_OK`)
- Wave 5 smoke **85/85**; UX **19/19** (remote + local)
- Category separation; missing/unsupported rule denial; effective-dated rule versioning
- Dual-approval override with evidence; recalculation after source/rule changes
- Approved worksheet history retained (immutable payload; supersede on recalc); residual **0**
- Regressions: Wave 4 **79/79**, Wave 3 **46/46**, Wave 2B **48/48**, Wave 2A **41/41**
- Rollback verified (Wave 5 drop-in cleared then redeployed); prior wave drop-ins retained
- Sibling freezes green (E360 / Onboarding / Attendance / Leave / Shifts)

## Explicit NO-GO (outside this freeze)

- Production synthetic / production deploy of Wave 5
- Remittance, payments, or real statutory filing
- Bank / WPS / AS’HAL execution
- Treating worksheets as payable or compliance authority
- Changes to frozen Wave 1/2A/2B/3/4 contracts or flows
- Next payroll wave (not started)

## Rollback

Staging drop-in:  
`/etc/systemd/system/wathefni-orchestrator-staging.service.d/zzzzzzzzzzzzzzzzz-payroll-wave5-pifss-eos.conf`  
(Remove → daemon-reload → restart; Wave 1–4 drop-ins retained. Schema tables remain additive.)
