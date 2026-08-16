# Compliance Wave 1 — Findings Contract Freeze

**Gate:** `PROD_SYNTHETIC_COMPLIANCE_WAVE1_FINDINGS_GO`  
**Evidence:** `ops/evidence/compliance-wave1b-prod-canary-20260803T163105Z/`  
**Freeze:** **GO** for Wave 1 Findings Contract (synthetic-only production posture)

## Frozen posture

- Document compliance only (not labor quotas, not Payroll statutory worksheets)
- `WATHEFNI_COMPLIANCE_WAVE1=1`, `SYNTHETIC_ONLY=1`, markers `CFW1` / phones `965541*`
- Evidence honesty: missing · uploaded · HR reviewed · expired/expiring — **never `government_verified`**
- No government APIs, filings, fine calculations, or legal-compliance claims
- `money_authority`: **false** (Compliance is not money authority)
- Alerts & Delivery owns reminder delivery
- Analytics remains frozen and excludes Compliance metrics
- Onboarding collects; Compliance owns expiry findings; Employees holds person context
- No AI; no frozen-module contract changes

## Proven on production synthetic

- ACK migrate (`compliance_wave_acks`) with production ACK
- Ranked findings, owner/escalation, residence/work-permit integrity, deep links
- Freshness / as_of (Asia/Kuwait), EN/AR, evidence honesty
- Manager scope isolation; residual canary ACK = 0
- Rollback verified; redeploy canary green
- Sibling freezes green (Analytics / Employees 360 / Onboarding / Attendance / Leave / Shifts / Payroll)

## Explicit NO-GO (outside this freeze)

- Compliance Wave 2
- AI assistant inside Compliance
- Government APIs / filing / fine engines / automatic legal-compliance claims
- Compliance metrics inside Analytics
- Reopening frozen module boundaries

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-compliance-wave1b-*`  
(Drop-in removal restores pre-Wave-1 Compliance flags; durable wave ACK rows retained.)
