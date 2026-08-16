# Wave D Phase 5 — Production deploy (mailbox connectors → durable pipeline)

**Stamp:** `20260801T155854Z`  
**Mode:** Production deploy of local-qualified D5 only. **No Wave D6. No GA.**  
**Local qualifier:** `ops/evidence/waveD-phase5-mailbox-connectors-durable-20260801T154944Z/` (PASS)  
**Remote evidence:** `/opt/wathefni/production-evidence/waveD-phase5-mailbox/20260801T155854Z`  
**Backup / rollback:** `/opt/wathefni/backups/production-pre-waveD-phase5-mailbox-20260801T155854Z`

---

## Verdict: **PASS**

| Gate | Result |
|---|---|
| Health orch + dashboard 200 | **PASS** |
| Gmail `gmail.readonly` only | **PASS** |
| M365 `Mail.Read` + `User.Read` + `offline_access` | **PASS** |
| Dedicated M365 mail-read app (not Calendar / not Mail.Send) | **PASS** |
| Sync disabled by default (`WATHEFNI_MAILBOX_SYNC=off`) | **PASS** |
| Premium + tenant-flagged; forwarding default | **PASS** |
| External tenants / GA fail-closed | **PASS** |
| Configured folder/mailbox only | **PASS** |
| Discovered mail → durable D2/D3 pipeline (`live_durable`) | **PASS** |
| No legacy `import_batches` / direct candidate creation | **PASS** |
| Duplicate sync idempotent | **PASS** |
| Incremental sync + cursor persistence | **PASS** |
| Pause / reconnect / token expiry / disconnect | **PASS** |
| Tenant-scoped Fernet secrets | **PASS** |
| Connector OFF fail-closed | **PASS** |
| Forwarding path unchanged | **PASS** |
| EN/AR + RTL desktop/mobile | **PASS** |
| Cleanup + rollback/restore | **PASS** |
| D6 not started | **PASS** |

**Prod API proofs:** `23/23` — `verify/prod-api-proofs.json`

---

## Production SHAs (final, post restore-new)

| Artifact | SHA-256 |
|---|---|
| `orchestrator/app.py` | `e4c2001736e18dc5e9352d45e44e519f61a242df660c0ee36d78ed391ff8a032` |
| `orchestrator/inbound_mailbox_connectors.py` | `523e705d6b48cc60150ef58c99cd2f6124eeccbf9a873f91793be56119784d5e` |
| `orchestrator/inbound_intake_product.py` | `fdca2310231bb78e3fd1aeb1ae3107880b56ce3e6244d91e985aa58d4e409294` |
| `dashboard/assets/SettingsPage-DBF5JtBV.js` | `87c8d7b374c8349b210023d0cbd56ff83d059c00ab4306f0eabfe5c4af54df94` |
| `dashboard/index.html` | `40e69eb49ce9ddc7241a689c0ae2846a220ca06072f477d639c98c2006211f48` |
| drop-in `waveD-phase5-mailbox-connectors.conf` | `52ad46e1e19f1e0aeecc53b5b44c2df77d2d4f8faa4e6cc69a44ba51769ba0df` |

Source: `verify/sha-final.txt`

---

## Connector / proof IDs

| ID | Value | Notes |
|---|---|---|
| Forwarding intake (create proof) | `2033e515-2516-4c7a-8678-bd3a626254a7` | Disabled in cleanup |
| Durable sync mailbox | `b3d4fa9a-fe09-44de-b220-8555633416ea` | Deleted after disconnect proof |
| Durable route intake | `2493b577-09e3-45c2-b923-b0c382c251df` | Existing Postmark default (unchanged active) |
| Provider message id | `d5prod-waveD5-prod-20260801T155854Z` | First sync durable=1; re-sync duplicate=1 |
| Secrets proof mailbox | `eceeb7d4-a3c0-4b2d-bc03-7c03f7d4feaa` | Deleted after Fernet ciphertext proof |

---

## Kept product constraints (live)

- **Default product:** forwarding (`default_intake_product=forwarding`)
- **Mailbox connectors:** premium (`mailbox_connectors_premium=true`), sync **off**
- **External tenants:** `WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI` (fail-closed `403`)
- **Gmail scopes:** `https://www.googleapis.com/auth/gmail.readonly`
- **M365 delegated scopes:** `Mail.Read`, `User.Read`, `offline_access` via dedicated `WATHEFNI_M365_MAILBOX_*` (not calendar SP, not Mail.Send)
- **Drop-in pin:** `Environment=WATHEFNI_MAILBOX_SYNC=off`

---

## Proof highlights

| Case | Evidence |
|---|---|
| Health | `orch=200` `dash=200` (`verify/health_final.txt`) |
| Live durable sync | `mode=live_durable`, counts durable=1; no `batch_id` |
| Folder only | label `Recruitment`, provider calls=1 |
| Idempotent duplicate | second sync: durable=0, duplicate=1 |
| Cursor | `after_epoch` persisted; `last_sync_status=ok` |
| Pause | `skipped=mailbox_paused` |
| Token / auth failure | `needs_reconnect` + `last_sync_status=error` |
| Disconnect | API 404 / connection gone |
| Connector OFF | `skipped=mailbox_sync_disabled` |
| Secrets | Fernet ciphertext len=120; plaintext absent; tenant=`WATHEFNI` (`verify/encrypted-secrets-proof.json`) |
| Forwarding unchanged | create intake `200` → `wathefni-cv-ca6616@inbound.wathefni.ai` |
| UI EN/AR | SettingsPage strings + screenshots `screenshots/connector-{en,ar}-{desktop,mobile}.png` |

---

## Cleanup proof

- Proof mailbox connection deleted (`mailbox_rows_left=0` / remaining WATHEFNI mailbox connections = 0 after proofs)
- Wave D5 forwarding proof intake **disabled**: `2033e515-2516-4c7a-8678-bd3a626254a7`
- **Active continuous intake left:** Postmark default `2493b577-09e3-45c2-b923-b0c382c251df` only  
- Source: `cleanup/cleanup-final.json`

---

## Rollback / restore proof

1. **ROLLBACK.sh** — removed D5 module + restored pre-D5 `app.py` / intake product / dashboard; health briefly unavailable during cutover (`verify/rollback.log`, `verify/sha-after-rollback.txt` shows pre-D5 `app.py` SHA `61d3d841…`)
2. **RESTORE_NEW.sh** — restored D5 orchestrator module + dashboard `SettingsPage-DBF5JtBV.js` + drop-in (`verify/restore-new.log`, `verify/sha-final.txt`)
3. Final health: **orch=200**, **dash=200**; sync still **off**

---

## Deploy note

Surgical production patch (not full local tree): `inbound_mailbox_connectors.py` (new), targeted `app.py` + `inbound_intake_product.py` updates, dashboard dist with connector card, systemd drop-in pinning sync off.

**Wave D6 was not started.**

---

## Evidence path

`ops/evidence/waveD-phase5-mailbox-connectors-deploy-20260801T155854Z/`
