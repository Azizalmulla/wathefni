# Settings Page Refinement Wave 1 — Production deploy (IA Closure amend)

**Stamp:** `20260804T153557Z`  
**Evidence:** `ops/evidence/settings-page-ia-closure-wave1-prod-deploy-20260804T153557Z/`  
**Freeze:** `ops/SETTINGS_PAGE_REFINEMENT_WAVE1_FREEZE.md`  
**Prior Wave 1 stamp:** `20260804T140349Z` (softened copy; long mixed scroll)  
**Live:** `SettingsPage-BkgjpPsv.js` (+ `PostHire-CbltSlA6.js`, `dashboard-D6sM7fYQ.js`)  
**Backup:** `/opt/wathefni/backups/production-pre-settings-page-ia-closure-wave1-20260804T153557Z/`  
**Prerequisite:** Activity Wave 1 frozen `20260804T135815Z`

## Verdict

| Gate | Result |
|---|---|
| Production UI deploy | **GO** |
| Safe smoke | **GO** (`SETTINGS_PAGE_WAVE1_SMOKE_OK`) |
| Activity regression | **GO** (`ACTIVITY_PAGE_WAVE1_SMOKE_OK`) |
| Amend Settings Page Wave 1 freeze | **GO / FROZEN** |
| Permission / backend authority | **NO-GO** (unchanged) |
| Final palette pass | **NO-GO** (not started) |

## Purpose

Manage who belongs here, how they sign in, and how Wathefni connects company tools — without changing role permissions or delivery ownership.

## IA Closure (UI-only)

Secondary navigation replaces the mixed-responsibility scroll:

1. **My account** — identity, logout, WhatsApp link, capabilities  
2. **Team & access** — invites, roles, directory; governed role/deactivate confirms with Activity audit context  
3. **Company** — hiring visibility + candidate-intake policy  
4. **Communications** — email sending, inbound document/CV addresses, mailbox  
5. **Integrations** — Google / Microsoft company connections (HR-facing)  
6. **Advanced** — admin-only backup access, legacy operator tools, sync projections, connection IDs, diagnostics  

Also:

- Removed duplicated page-level purpose (shell subtitle remains)  
- Setup instructions behind **Setup guide** / **Learn how**  
- Plain language outside Advanced (no Ensure legacy operator / C6B / platform_integration_disconnected)  
- Preserved all permission gates and mutate APIs  

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-settings-page-ia-closure-wave1-20260804T153557Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-settings-page-ia-closure-wave1-20260804T153557Z
```
