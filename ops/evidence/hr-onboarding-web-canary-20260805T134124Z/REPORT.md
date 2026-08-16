# HR Onboarding Web — Canary Correction

**Stamp:** `20260805T134124Z`  
**Scope:** HR Onboarding queue/detail only — shared lifecycle projection, writers, permission gates, drawer + portal menu. Web shell/visual system unchanged. Frozen pages untouched.  
**Live bundle:** `PostHire-BlCa__DP.js`  
**API:** `https://api.wathefni.ai` (health OK after syntax hotfix)

## What shipped

### Backend
- `GET /dashboard/posthire/onboarding/{employee_key}` returns shared Wave 2A **HR web projection** (`items` + collapsed `available_tasks`) plus `permission_authority` / subject markers.
- Mark complete → `accepted` via `set_item_lifecycle` (legacy `received` maps to `accepted` when lifecycle on).
- HR upload landing → `processing` (never ambiguous legacy `received` under Wave 2A).
- `cancel_onboarding` / `reschedule_onboarding` mapped to `onboarding.manage` in `TOOL_PERMISSION_MAP`.

### Frontend
- Queue opens checklist in **Leave-style drawer** (no inline row expansion / queue jump).
- Shared `OnboardingPrimaryButton` for Remind / Review / Open / View.
- Three-dot menu via **portal** (`OnboardingOverflowMenu`) — closes on outside click, Escape, scroll, resize, navigation.
- Dormant optionals only under collapsed **Available tasks**.
- Mark complete sends `accepted`; upload gated on `onboarding.manage` + `doc_upload_enabled` (not HR_MUTATE AND).
- Confirmation retry merges original args so `employee_key` / `item_id` are never dropped.

## Canary qualification (`CANARY_QUAL_OK`)

| Check | Result |
|---|---|
| Owner session `permission_authority=backend_current` | Pass (user `88b17ca9-…`) |
| Projection `hr_web` / lifecycle `2a` | Pass — main **5**, available **27** |
| Dormants hidden by default | Pass |
| Owner reschedule | Pass |
| Owner mark → `accepted` (restored to `processing`) | Pass |
| Restricted viewer (Faisal) mutate actions empty | Pass |
| Viewer mark HTTP 403 fail-closed | Pass |
| Tenant isolation (wrong company) | Pass 403 |
| Audit (`onboarding_audit_events`) | Pass (3 recent) |
| Lifecycle parity shared statuses | Pass (earlier API smoke) |
| Local Wave 2A smoke on prod | Pass |

**Roles:** Aziz owner · Faisal viewer  

## Rollback

```bash
/opt/wathefni/backups/production-pre-hr-onboarding-web-canary-20260805T134124Z/ROLLBACK.sh
```

Restores prior orchestrator files + dashboard dist (`/opt/wathefni/dashboard-dist` and `/var/www/wathefni-dashboard`).

## Incident note (deploy)

First `app.py` push briefly crash-looped on a typo (`||` instead of `or`). Restored from bak within minutes; fixed file redeployed via `rsync -z`. Health verified active before qualification.

## Evidence

- Local: `ops/evidence/hr-onboarding-web-canary-20260805T134124Z/`
- Remote bak: `/opt/wathefni/backups/production-pre-hr-onboarding-web-canary-20260805T134124Z/`
- Verify: `verify/owner-mutation-ok.json`, `verify/canary-api-smoke.json`

## Owner live review

Ready — open Post-hire → Onboarding as Aziz (owner) and Faisal (viewer). Confirm drawer, Available tasks, portal menu, and action visibility.
