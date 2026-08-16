# Wave D Phase 4 — Production deploy (inbound CV alias and admit UX)

**Verdict: PASS**  
**Stamp:** `20260801T152150Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  
**Wave D5:** not started  
**External tenants:** not enabled

Local evidence: `/Users/azizalmulla/Desktop/claw/ops/evidence/waveD-phase4-inbound-alias-admit-ux-deploy-20260801T152150Z`  
Remote evidence: `/opt/wathefni/production-evidence/waveD-phase4-alias-admit/20260801T152150Z`  
Backup: `/opt/wathefni/backups/production-pre-waveD-phase4-alias-admit-20260801T152150Z`

---

## Production SHAs (final, after rollback→restore)

```
c4c5227716d504777128737eef4f0414664efdf9046454b71dcb0ca6f28c75ad  /var/www/wathefni-dashboard/assets/SettingsPage-CtnZVrSW.js
2bebdd49fe953ac822ac967482042691b7aea0769d4a48ca290b8ef8282b612c  /var/www/wathefni-dashboard/assets/CandidatesPage-CpHnUIxl.js
e20031c7529a29b0571afe06e7df1ca1aa155a8d4e957c4f22863cacd148c245  /var/www/wathefni-dashboard/assets/inboundIntakePresentation-B5lLioGw.js
6f72c204a853422e465b991a12d8571a1bdbf48c6f96550a12c15e8aae42aed7  /var/www/wathefni-dashboard/index.html
```

Match local qualified source SHAs: **yes** (`verify/local-qualified.sha256` matches D4 local qualification `waveD-phase4-inbound-alias-admit-ux-20260801T134856Z`).

Orchestrator D2/D3 safety modules: **unchanged** (`before/orchestrator-d3.sha256` == `after/orchestrator-d3.sha256`).

---

## Scope shipped

| Artifact | Action |
|---|---|
| Dashboard dist | **Deployed** — Settings general/job alias UX + Held Intake review in Candidates |
| `inboundIntakePresentation-*.js` | **New chunk** — EN/AR hold labels + quarantine recovery |
| Orchestrator / D3 drop-ins | **Unchanged** |

No Intake Operations console restored.

---

## Enablement posture

- `WATHEFNI_INBOUND_EMAIL=on`
- `WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI`
- `WATHEFNI_MAILBOX_SYNC=off`
- External companies fail closed
- **D5 not started**

---

## Proof gates

| Gate | Result |
|---|---|
| Health 200 (orchestrator + dashboard) | **PASS** (`health_final=200`, `dashboard_final=200`) |
| Settings create general → `needs_role` / Needs a job | **PASS** |
| Settings create job-specific alias → `role_bound` / Bound to a job | **PASS** |
| Held Intake review API in Candidates workflow | **PASS** |
| Single assign-and-admit | **PASS** (`ready_for_review`) |
| Safe bulk admit | **PASS** (bulk `assign` → promoted) |
| Duplicate provider message | **PASS** |
| Identity + quarantine labels / recovery copy | **PASS** (live bundle + Candidates UI) |
| EN/AR + RTL desktop/mobile screenshots | **PASS** (UI 4/4) |
| Permissions / tenant isolation | **PASS** (cross-tenant inspect 403; ACMECORP create 403) |
| Intake Operations absent | **PASS** |
| D2/D3 safety controls unchanged | **PASS** |
| Rollback verified | **PASS** (pre SHAs restored; restore-new returns D4 SHAs; health 200) |

Sources: `verify/prod-api-proofs.json` (25/25), `verify/prod-ui-proofs.json` (4/4), `verify/rollback.log`, `verify/restore-new.log`.

---

## Screenshots

`screenshots/`

| File | View |
|---|---|
| `prod-en-desktop-settings.png` | EN desktop Settings alias UX |
| `prod-en-desktop-candidates.png` | EN desktop Held Intake card |
| `prod-ar-desktop-settings.png` | AR desktop RTL Settings |
| `prod-ar-desktop-candidates.png` | AR desktop Held Intake |
| `prod-en-mobile-settings.png` | EN mobile Settings (via More) |
| `prod-en-mobile-candidates.png` | EN mobile Held Intake |
| `prod-ar-mobile-settings.png` | AR mobile Settings |
| `prod-ar-mobile-candidates.png` | AR mobile Held Intake |

Note: Held card screenshots used a mocked empty-queue `import/intake` payload against the **live production dashboard bundle** after admit cleanup emptied the queue. Alias create/admit/isolation proofs were live API.

---

## Rollback

- Scripts: `rollback/ROLLBACK.sh`, `rollback/RESTORE_NEW.sh`
- Rollback restored pre-D4 Settings/Candidates chunks (`SettingsPage-BmkZSLcI.js`); D4 markers absent
- Restore-new returned D4 SHAs above; health 200

---

## Cleanup

- All `waveD4-prod-proof*` / UI-seed intake addresses **disabled**
- Continuous WATHEFNI active intake remains **1** (Postmark default test)
- Two pre-existing held imports were admitted to `OCCTST_044035` during proof and remain `ready_for_review` (documented in `cleanup/cleanup-final.json`)

---

## Final

**PASS** — Wave D Phase 4 alias + admit UX live for WATHEFNI/test allowlist only. External tenants disabled. D5 not started.
