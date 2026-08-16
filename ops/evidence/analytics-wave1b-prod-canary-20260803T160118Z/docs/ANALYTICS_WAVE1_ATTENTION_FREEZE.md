# Analytics Wave 1 — Attention Contract Freeze

**Gate:** `PROD_SYNTHETIC_ANALYTICS_WAVE1_ATTENTION_GO`  
**Evidence:** `ops/evidence/analytics-wave1b-prod-canary-20260803T160118Z/`  
**Freeze:** **GO** for Wave 1 Attention Contract (synthetic-only production posture)

## Frozen posture

- Analytics is **read-only**
- `WATHEFNI_ANALYTICS_WAVE1=1`, `SYNTHETIC_ONLY=1`, markers `ANW1` / phones `965540*`
- Money authority / `money_authority`: **false** (no payroll cost analytics)
- Hiring Reports remain separate
- Alerts & Delivery owns communication/delivery operations
- No AI, no Compliance metrics, no frozen-module contract changes

## Proven on production synthetic

- ACK migrate (`analytics_wave_acks`) with production ACK
- Actor identity on dashboard analytics read
- Ranked attention, partial-module disclosure, masked counts, deep links
- Freshness / as_of (Asia/Kuwait), EN/AR definitions, mobile-web responsive tokens
- Rollback verified; redeploy canary green; residual canary ACK = 0
- Sibling freezes green (Employees 360 / Onboarding / Attendance / Leave / Shifts / Payroll)

## Explicit NO-GO (outside this freeze)

- Analytics Wave 2
- AI assistant inside Analytics
- Compliance metrics in Analytics
- Payroll money / cost analytics
- Broad non-synthetic analytics mutations (none exist; keep read-only)

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-analytics-wave1b-*`  
(Drop-in removal restores pre-Wave-1 flags; durable wave ACK rows retained.)
