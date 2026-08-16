# Bank ESS + onboarding-completion UI — Phase 1B live deploy

**Stamp:** `20260806T170025Z`  
**Verdict:** `deployed`  
**Phase 2 qualification:** not started  
**Auth Wave 2:** not started  

## Release

| Item | Value |
|---|---|
| Branch | `release/bank-ess-ui-clean-20260806T155845Z` |
| Tip | `6547a25883609cbe84ca2f25bb8b2ea24afedce6` |
| Feature commit | `5509e64ea81765f41e1786b16db507ad79d6d0c6` |
| Pre-deploy gate | PASS (`predeploy/GATE.txt`) |

## Dashboard

| Item | Value |
|---|---|
| Previous | `PostHire-6LCFY5pA.js` SHA `406b9dca3d05926dcaf0c3390c960e72c42d58bf5883b3d8f47b209be935dab1` |
| Deployed | `PostHire-BRA7Ln_S.js` SHA `e833ce5c8ec7b1a77165848028b53a39f298fd3267de4c20179d5ebb62005317` |
| Backup | `/opt/wathefni/dashboard-dist-bak/bank-ess-ui-20260806T170025Z/` |
| Deploy | `rsync -a --delete <release-dist>/ root@76.13.63.68:/var/www/wathefni-dashboard/` |
| Rollback | `dashboard/ROLLBACK.sh` → restore backup |
| Public asset | `https://api.wathefni.ai/dashboard/assets/PostHire-BRA7Ln_S.js` **200** |
| Health | orchestrator `http://127.0.0.1:8010/health` **200** |

### Live smoke (API + asset)

- PostHire bundle contains OCR + Compliance + Bank Review + Completion Strip needles — PASS (`smoke/ocr-bank-live-asset.txt`)
- HR bank review GET EN/AR — PASS
- HR onboarding-completion GET EN/AR — PASS
- Compliance findings+register+summary payload — PASS
- Employee profile + documents — PASS
- Employee `/app/bank` + `/app/onboarding` EN/AR (no submit) — PASS
- Permissions: unauth bank denied 401 — PASS
- Temp allowlist canary cleaned — PASS
- Summary: **21/21** (`smoke/live-api-smoke.txt`)

## Employee mobile

| Item | Value |
|---|---|
| Delivery | **OTA** (JS-only; no native dep delta) |
| Runtime | `0.1.0` |
| Channel / branch | `canary` |
| Update group | `326e2040-6603-4c34-a6db-1022ff8095a6` |
| iOS update | `019fd80f-3cc8-7905-8863-2c4cefed9e4b` |
| Android update | `019fd80f-3cc8-75bd-8b6e-d7cfed86c919` |
| Release commit (source) | `6547a25` (+ packaging/`src/lib/refresh.tsx` build dep) |
| Rollback | `mobile/ROLLBACK.sh` (`eas update:rollback` group above) |

### Mobile smoke

- Capability foundation GREEN on OTA tree
- OTA source maps contain bank + completion contracts — PASS
- Live HTTP EN/AR bank + onboarding completion — PASS (same API smoke)
- **Physical canary device force-close/reopen walk:** not executed in this agent session — owner should force-close Wathefni once to pull OTA, then open Bank + Onboarding (no bank submit)

## OCR regression

Live PostHire asset retains:
`Extraction & validation summary`, `never overwrite`, `data-document-extraction-summary`, `data-compliance-findings`, `data-compliance-register`, `data-compliance-summary`

## Remaining risks

1. Owner device OTA pull not agent-stamped (force-close required).
2. OTA tree is release mobile + production packaging; `src/lib/refresh.tsx` pulled as build dependency of release `_layout.tsx`.
3. Full Bank ESS lifecycle / completion qualification (Phase 2) not run.
4. Auth Wave 2 still blocked until Phase 2 completes.

## Evidence root

`ops/evidence/bank-ess-ui-clean-deploy-live-20260806T170025Z/`
