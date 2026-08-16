# Compliance Page Refinement Wave 1 — FREEZE

**Status:** FROZEN  
**Deploy stamp:** `20260804T084521Z`  
**Evidence:** `ops/evidence/compliance-page-refinement-wave1-prod-deploy-20260804T084521Z/`  
**Report:** `ops/COMPLIANCE_PAGE_REFINEMENT_WAVE1.md`  
**Live bundle:** `/var/www/wathefni-dashboard/assets/PostHire-CTpKApnh.js`  
**Prerequisite findings freeze:** `ops/COMPLIANCE_WAVE1_FINDINGS_FREEZE.md` (backend findings contract unchanged)

## Frozen surface

- Purpose: resolve missing, expiring, expired, and review-required employee documents through one clear workflow
- Findings-first IA; All documents demoted behind a surface tab
- Filters: Needs review · Missing · Expiring · Expired · All
- One reminder path on Findings (`compliance_send_reminder`); register routes via Open in Findings
- Delivery strip excluded on Compliance
- D3–D6 replaced with governed Wathefni modals (`withReason` + dates modal)
- Employees 360 Compliance section is context + deep-link only
- Methodology / authority collapsed; HR reviewed ≠ government verified
- `lang` + RTL when Arabic; cream/ink visual direction preserved
- Permissions: `compliance.manage` for review/remind; upload still `onboarding.manage` when enabled

## Frozen non-goals

- Changing document extraction, OCR, classification, or Mistral identity authority
- Changing compliance findings ranking / builder contracts
- Government verification claims or PACI/MOI/PAM integrations
- Employees D1–D2 native dialogs
- Reopening Analytics / Payroll / Shifts / Leave / Attendance / Onboarding page freezes
- Final palette refinement

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-compliance-page-refinement-wave1-20260804T084521Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-compliance-page-refinement-wave1-20260804T084521Z
```
