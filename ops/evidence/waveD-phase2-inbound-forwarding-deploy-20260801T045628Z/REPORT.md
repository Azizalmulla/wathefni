# Wave D Phase 2 — Production deploy (forwarded inbound control plane)

**Verdict: PASS**  
**Stamp:** `20260801T045628Z`  
**Host:** `root@76.13.63.68`  
**Dashboard:** `https://api.wathefni.ai/dashboard/`  
**Wave D3:** not started  
**External tenants:** not enabled

Local evidence: `/Users/azizalmulla/Desktop/claw/ops/evidence/waveD-phase2-inbound-forwarding-deploy-20260801T045628Z`  
Remote evidence: `/opt/wathefni/production-evidence/waveD-phase2-inbound/20260801T045628Z`  
Backup: `/opt/wathefni/backups/production-pre-waveD-phase2-inbound-20260801T045628Z`

---

## Production SHAs (final, after rollback→restore)

```
c3f1b91cadf8ec03b3fa0098b093e5bd5b645ca0fe58c1ef37326b8ceeb39ab2  /opt/wathefni/orchestrator/app.py
dc48349ce329624fc05654b9bf2f6268987eb24add7f7ad20cc554fa0dc06c36  /opt/wathefni/orchestrator/inbound_intake_product.py
717b3482dc8811f2b3f27f0aac5c21869d56e96fba0ba57e647b025e7d234036  /opt/wathefni/orchestrator/durable_email_ingress.py
d5f29e9a4df3ca83de948dffad4b7f6de964b7facb48962c016db171942b6880  /opt/wathefni/orchestrator/tenant_email_authority.py
86e97c3575ee6855f971e493f7c9d036eb2d573d8a239b2784bbeda4bf286e35  /var/www/wathefni-dashboard/assets/SettingsPage-BmkZSLcI.js
```

Match local qualified SHAs: **yes** (`verify/local-qualified.sha256` ↔ `verify/sha-final.txt`).

---

## Scope shipped

| Artifact | Action |
|---|---|
| `inbound_intake_product.py` | **New** |
| `app.py` | D2 control-plane only (13 hunks vs prod baseline) |
| `durable_email_ingress.py` | Tenant quota override hook |
| `tenant_email_authority.py` | Intake feature/setup steps enrichment |
| Dashboard dist | Settings intake create/copy/rotate/disable + EN/AR copy |
| systemd drop-in `waveD-phase2-inbound-allowlist.conf` | `WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI`, `WATHEFNI_MAILBOX_SYNC=off` |

---

## Enablement posture

- `WATHEFNI_INBOUND_EMAIL=on` (unchanged continuous freeze)
- `WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI` (explicit)
- Test-looking tenants still permitted only via default-allowlist equality heuristic (`INBOUND*`, `*TEST*`)
- `WATHEFNI_MAILBOX_SYNC=off`
- External companies fail closed (`ACMECORP` denied)
- No D3 commercial quota enablement

---

## Test address IDs (created then disabled)

| Role | intake_id | address | hold_policy |
|---|---|---|---|
| General (pre-rotate) | `e40df0d2-6d0a-4da0-9780-ca13cfab9ba6` | `wathefni-cv-1cb7e3@inbound.wathefni.ai` | needs_role → disabled by rotate |
| Job alias | `80da2266-f722-4084-aadb-3b525cccb309` | `wathefni-d2-44a79e@inbound.wathefni.ai` | **role_bound** → disabled |
| General (post-rotate) | `c3f26ffd-bd5f-423e-82c2-923e301ed7e8` | `wathefni-cv-d11603@inbound.wathefni.ai` | **needs_role** → disabled |

---

## Proof gates

| Gate | Result |
|---|---|
| Health 200 (orchestrator + dashboard) | **PASS** (`health_final=200`, `dashboard_final=200`) |
| Settings intake card EN/AR desktop/mobile | **PASS** (UI 4/4; no Intake Operations) |
| Create / inspect / rotate / disable / copy | **PASS** |
| Cross-tenant access | **PASS** (403 `dashboard_company_forbidden` for ACMECORP inspect/disable; own tenant 200) |
| Non-allowlisted fail closed | **PASS** (create as ACMECORP → 403) |
| Disabled/rotated no longer resolve | **PASS** (all 3 proof addresses `resolves=false`) |
| General → needs_role | **PASS** |
| Job alias → role_bound | **PASS** |
| Postmark → durable ingress | **PASS** (`durable=true`, `status=queued`, company WATHEFNI) |
| Quarantine + malware scan | **PASS** (`stored` + `safety_state=clean` via ClamAV) |
| OCR/extraction + identity (prod Mistral) | **PASS** (extracted email+phone; outcome `possible_match` / HR review — **not** `mistral_disabled`) |
| Duplicate handling | **PASS** (`duplicate=true` on replay) |
| Explicit HR admit | **PASS** (`POST /import/items/assign` → `ready_for_review`) |
| Mailbox sync off | **PASS** |
| Schema partial unique index | **PASS** (`idx_intake_addresses_local_active`; legacy `idx_intake_addresses_local` dropped) |
| Rollback verified | **PASS** (rollback to pre SHAs + module removed; restore-new returns D2 SHAs; health 200) |

### OCR note

Local qualification was blocked by disabled Mistral OCR. Production has `WATHEFNI_CV_MISTRAL_OCR=true` + `mistral.env`. Proof CV extracted `waved2…@example.com` / phone and produced an identity resolution without `ocr_required_mistral_disabled`.

---

## Cleanup proof

- Admitted synthetic app `imp-wathefni-6fe7c151f3f171aa-WATHEFNI-IMPORT` deleted under authority cleanup
- Matching candidate deleted
- Remaining `waved2.*` apps: **0**
- Proof intake addresses left **disabled** (not active routing): see `cleanup/cleanup-final.json`
- Continuous pre-existing WATHEFNI intake address untouched (active count remains the production continuous recipient)

---

## Rollback

- Scripts: `rollback/ROLLBACK.sh`, `rollback/RESTORE_NEW.sh`
- Exercise: pre SHA `123b1496…` (app.py) on rollback; post-restore matches D2 SHAs above
- Env drop-in removed on rollback, restored on RESTORE_NEW

---

## Final

**PASS** — Wave D Phase 2 control plane live for WATHEFNI/test allowlist only. D3 not started.
