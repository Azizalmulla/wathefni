# Employee Onboarding Wave 2A — Final Cleanup

**Stamp:** `20260805T114246Z`  
**Scope:** Global EN=LTR / AR=RTL · hide Expo Router headers · hide dormant optional checklist items · single rejection reason · canary deploy · Aziz smoke · internal iOS build.  
**Out of scope:** bank ESS submit/auth, allowlist expansion, OCR/template waves.

## Backend (prod canary)

- Deployed `onboarding_lifecycle_wave2a.py` (+ local smoke).
- Backup: `/opt/wathefni/backups/production-pre-onboarding-wave2a-cleanup-20260805T114246Z`
- Flags unchanged (Aziz + Talal only):
  ```
  WATHEFNI_ONBOARDING_LIFECYCLE_V2A=on
  WATHEFNI_ONBOARDING_LIFECYCLE_V2A_COMPANIES=WATHEFNI
  WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST=WATHEFNI-96599338566,WATHEFNI-96550252254
  ```
- Optional visibility: hide `required=false` unless active (submitted/processing/accepted/replacement/…) **or** has evidence **or** `lifecycle_meta.explicitly_assigned|applicable`. Seed `due_date` alone does **not** surface dormants.
- Bank remains visible with empty actions (informational).

## Aziz prod smoke (`AZIZ_SMOKE_OK` / `EN_AR_API_SMOKE_OK`)

| item | status | section |
|---|---|---|
| civil_id | accepted | completed |
| employment_contract | replacement_required + reason + resubmit/preview/versions | your_actions |
| personal_photo | processing | being_reviewed |
| offer_letter | processing (file evidence) | being_reviewed |
| bank_details | pending, actions=[] | your_actions |

Hidden dormants include passport/residence/work_permit/personal_details_form/emergency_contact and HR rails without evidence.

Rejection reason appears once on the contract item (API field single; mobile no longer duplicates into guidance).

## Mobile

- Root `direction` + `I18nManager` sync on locale change / auth transitions (login, logout, blocked).
- All Stack + Tabs screens `headerShown: false`; Page `safeTop` defaults true.
- Contract card: rejection reason XOR guidance (not both).

## Internal iOS build

- Profile: `production` (internal, `https://api.wathefni.ai`)
- buildNumber: **7**
- EAS: https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/78a25dd7-0731-4e27-95fe-f7f44b532c51

## Activation (fresh)

- phone field: `99338566`
- code: `356216`
- invite: `656c327b-f81b-4e62-a5f6-d345c45f274b`

## Rollback

1. Flag: `WATHEFNI_ONBOARDING_LIFECYCLE_V2A=off` + restart orchestrator.
2. Module: restore from backup dir above.
3. Mobile: prior internal IPA (build 6 / projection stamp `20260805T045200Z`).
