# Wave C — entitlement + Assistant email — production deploy

**Verdict: PASS**
**Stamp:** `20260801T042210Z`
**Host:** `root@76.13.63.68`
**Dashboard:** `https://api.wathefni.ai/dashboard/`
**Wave D:** not started

## Production SHAs (after deploy)

```
c2494eda6a7d41334ba1f7ca8e8648e5f7c6ea7fef7fee5555e5776a54234caf  /opt/wathefni/orchestrator/assistant_capability_catalog.py
a87e5bfb44f5a896c25f9efc4d2d0e28addf5bcfcf85d97ee5519a8cb4417016  /opt/wathefni/orchestrator/action_registry.py
c7c7a8727c20b80f5e024189eca7511fb17569e10a0d4540ff60ea261f29edd0  /opt/wathefni/orchestrator/workspace_capability.py
f5c86cb1caef8a8a4d53463c2367bbe143592dba2d2ac3034531895322abac3f  /var/www/wathefni-dashboard/assets/dashboard-CmztGRNg.js
74c14abe376bbe6ddc322e64d58aa64270eeb948cb53dce252faa5e92c57162a  /opt/wathefni/orchestrator/offer_service.py
72c492297e1aaa36da6d35356a0dde70b9a5431d74c6885278f07ef4cc0e13ba  /opt/wathefni/orchestrator/operator_mobile.py
```

### Orchestrator (qualified local match)

| Artifact | SHA-256 |
|----------|--------|
| `assistant_capability_catalog.py` | `c2494eda6a7d41334ba1f7ca8e8648e5f7c6ea7fef7fee5555e5776a54234caf` |
| `action_registry.py` | `a87e5bfb44f5a896c25f9efc4d2d0e28addf5bcfcf85d97ee5519a8cb4417016` |
| `workspace_capability.py` | `c7c7a8727c20b80f5e024189eca7511fb17569e10a0d4540ff60ea261f29edd0` |
| dashboard chunk `dashboard-CmztGRNg.js` (patched) | `f5c86cb1caef8a8a4d53463c2367bbe143592dba2d2ac3034531895322abac3f` |

## Scope shipped

| Change | Deployed? |
|--------|-----------|
| Assistant Postmark / wathefni email-readiness | **Yes** (`assistant_capability_catalog.py`) |
| Interviews ActionSpec entitlement (`module=interviews`) | **Yes** (`action_registry.py`) |
| Workspace nav authority | **Yes** (`workspace_capability.py` + dashboard App/JS patch) |
| Expired offer preview rejection | **Already on prod** (kept; local overwrite would regress) |
| Assessments mobile omit | **Already on prod** (kept; local rewrite would drop C2 surfaces) |

## Gates

| Gate | Result |
|------|--------|
| Health / dashboard | **200** (health_final=200 / dashboard_final=200) |
| Assistant email configured when wathefni/ready | **PASS** |
| Branded Microsoft/company-domain fail-closed when not ready | **PASS** |
| Expired offer preview rejected | **PASS** |
| Interview tools hidden + blocked when interviews OFF | **PASS** |
| Interview tools work when ON | **PASS** |
| Assessments omitted when OFF | **PASS** |
| Direct URLs fail closed | **PASS** |
| EN/AR desktop/mobile UI | **PASS** (7/7) |
| Backend prod proofs | **PASS** (28/28) |
| Former 15 FAIL family | **PASS** |
| Full entitlement matrix | **561/561 PASS** |
| Rollback → restore-new | **PASS** |

## Screenshots

- `screenshots/prod-ar-desktop-overview-rtl.png`
- `screenshots/prod-ar-mobile-assessments-off.png`
- `screenshots/prod-ar-mobile-more.png`
- `screenshots/prod-en-desktop-direct-interviews-off.png`
- `screenshots/prod-en-desktop-interviews-on.png`
- `screenshots/prod-en-desktop-overview.png`
- `screenshots/prod-en-mobile-more.png`

## Backup / rollback

- Backup: `/opt/wathefni/backups/production-pre-waveC-entitlement-20260801T042210Z`
- Scripts: `rollback/ROLLBACK.sh`, `rollback/RESTORE_NEW.sh`
- Exercise: rolled back ActionSpecs to `pre_hiring`, then restored Wave C SHAs; health **200** after restore

## Evidence

- Local: `/Users/azizalmulla/Desktop/claw/ops/evidence/waveC-entitlement-deploy-20260801T042210Z`
- Remote: `/opt/wathefni/production-evidence/waveC-entitlement/20260801T042210Z`

## Final

**PASS**
