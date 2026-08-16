# Settings Page Refinement Wave 1 — FREEZE (IA Closure amend)

**Status:** FROZEN  
**Prior freeze stamp:** `20260804T140349Z`  
**IA Closure stamp:** `20260804T153557Z`  
**Evidence:** `ops/evidence/settings-page-ia-closure-wave1-prod-deploy-20260804T153557Z/`  
**Report:** `ops/SETTINGS_PAGE_REFINEMENT_WAVE1.md`

## Frozen surface

- Purpose: access, sign-in, and company tool connections  
- IA: secondary nav — My account · Team & access · Company · Communications · Integrations · Advanced (admin-only)  
- UI/IA/copy/i18n only — same `users.manage` / `settings.manage` / `calendar.sync` / `candidate.import` gates  
- Same invite, role, visibility, email, mailbox, and platform APIs  
- Module launch stays Setup Console; delivery failures stay Alerts & Delivery  
- Cream/ink direction preserved  

## Frozen non-goals

- New roles/permissions or role-pack changes  
- Moving integration authority or Setup Console ownership  
- Wave D email/mailbox pipeline authority changes  
- Final palette refinement  

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-settings-page-ia-closure-wave1-20260804T153557Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-settings-page-ia-closure-wave1-20260804T153557Z
```
