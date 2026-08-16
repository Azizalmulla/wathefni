# Compliance Wave 1 — Findings Contract (staging)

**Stamp:** 20260803T162438Z  
**Evidence:** `ops/evidence/compliance-wave1-20260803T162438Z/`  
**Gate:** `STAGING_COMPLIANCE_WAVE1_FINDINGS_GO`

## Scope shipped
- Ranked document findings: severity, EN/AR reason, employee, team/location, document type, guidance-only rule label, owner, deadline, escalation, SoA deep link
- `as_of`, Kuwait date/window, freshness / stale honesty
- Evidence status: missing · uploaded · HR reviewed · expired/expiring — **never government verified**
- Residence / work-permit vocabulary + Art.18 seed / dual-write integrity
- Configurable owner by document type (`WATHEFNI_COMPLIANCE_OWNER_BY_TYPE`), default company HR/Compliance
- Read-only deep links into Compliance, Onboarding, Employees
- Full EN/AR findings UI; empty / loading / error / stale states
- Alerts & Delivery remains reminder delivery owner
- Analytics freeze intact (`compliance_metrics: false`)

## Explicit out of scope
AI, government APIs, filing, fine calculations, legal-compliance claims, Compliance metrics in Analytics, production deploy, frozen module authority changes.

## Proof
- Local: `smoke-test-compliance-findings-wave1.py` passed
- Sibling freezes: Analytics / Employees 360 / Onboarding / Attendance / Leave / Shifts green (staging re-proof after analytics canary sync)
- Staging health active; UI copy present (Findings by severity / Never government verified)
- Integrity: `residency_iqama` → `residence`; Art.18 seed includes `residence` + `work_permit`

## Next gate (not this wave)
Production synthetic qualification may proceed under a separate Wave 1-B plan (`PROD_SYNTHETIC_COMPLIANCE_WAVE1_FINDINGS_*`) — **not executed here**.
