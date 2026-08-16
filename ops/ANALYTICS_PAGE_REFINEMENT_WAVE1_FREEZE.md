# Analytics Page Refinement Wave 1 — FREEZE

**Status:** FROZEN  
**Deploy stamp:** `20260804T083205Z`  
**Evidence:** `ops/evidence/analytics-page-refinement-wave1-prod-deploy-20260804T083205Z/`  
**Report:** `ops/ANALYTICS_PAGE_REFINEMENT_WAVE1.md`  
**Live bundle:** `/var/www/wathefni-dashboard/assets/PostHire-CoNDfF7D.js`  
**Prerequisite attention freeze:** `ops/ANALYTICS_WAVE1_ATTENTION_FREEZE.md` (backend contract unchanged)

## Frozen surface

- Analytics purpose: workforce patterns, changes, and risks — **not** a daily task queue
- Insight-first IA: period chrome → snapshot → narrative → trends → collapsed methodology
- Duplicate Needs Attention inbox removed; deep-link strip to Needs Attention only
- Delivery strip excluded on Analytics
- Kuwait MTD window displayed; comparison is display-only “This period”
- Partial / stale states when dirty; healthy source-ok noise hidden
- `lang` + RTL when Arabic
- `GET /dashboard/posthire/analytics` payload consumed as-is (attention still fetched for count/deeplink only)

## Frozen non-goals

- Changing attention ranking, IDs, definitions, or Action Inbox merge
- Interactive date range / prior-period compare APIs
- AI, Compliance metrics, payroll money analytics
- Analytics Wave 2
- Employees deferred native dialogs (D1–D6)
- Reopening Payroll / Shifts / Leave / Attendance / Onboarding page freezes

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-analytics-page-refinement-wave1-20260804T083205Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-analytics-page-refinement-wave1-20260804T083205Z
```
