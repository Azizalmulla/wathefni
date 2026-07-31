# Hybrid Email Phase 1 — production-DARK deploy

**Verdict: PASS**  
**Stamp:** `20260731T010458Z`  
**Host:** `root@76.13.63.68`  
**Local git HEAD (dirty tree deploy):** `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2`

## Production artifact SHA256

| File | SHA256 |
|---|---|
| `app.py` | `16e08d766554e372fef88f96df61b8bd8a99cd1b7df667dd5170253d6f64d0a1` |
| `action_registry.py` | `a76082655031691d2eee708bc9323059b4b9f13e0b3d098c0c63fa40d5b14bb5` |
| `tenant_email_authority.py` | `052acd59e095cba9a7668c3fcf2b4564abd9a67c88f8fe844edd9bbff5d7a2c7` |
| `microsoft_mail_send.py` | `e76b21bbec0ccc38fa8ae28d1c6f1006bb12511526d7154ac7e71bef3804bd3e` |

Source: `remote/FINAL_SHA256_AFTER_TRUE_PRE.txt` (matches local artifacts).

Dashboard bundle markers: `SettingsPage-Dp-jwQs7.js`, `setupConsole-h-F2RppN.js` (`remote/dashboard_bundle_probe.txt`).

## Migration evidence (additive only)

```
tables= ['company_email_domains', 'company_email_settings', 'company_operational_mailboxes']
delivery_cols= ['provider', 'provider_accept_status', 'purpose', 'sender_mode', 'visible_from', 'visible_reply_to']
emergency_fallback_col= True
SCHEMA_ADDITIVE_OK
```

Live row counts after deploy: `company_email_settings=0`, `company_operational_mailboxes=0`, `company_email_domains=0` (no tenant mode activation).

## Dark invariants preserved

| Invariant | Evidence |
|---|---|
| Outbound Wathefni/Postmark | `from=hr@wathefni.ai`, provider=postmark, Postmark server HTTP 200 |
| Inbound Postmark | `WATHEFNI_INBOUND_EMAIL=on`, durable ingress import OK |
| Microsoft mail SP unset | `WATHEFNI_M365_MAIL_*=unset`, `mail_send_not_configured` |
| No branded modes | branded_active=0, settings_rows=0 |
| Emergency fallback default false | emergency=0 |
| Calendar client still present | calendar_client_present=True; calendar module does not import mail send |
| No Mail.Send grant / no tenant sender config | not provisioned; activation blocked `mode_not_ready` |

## Smoke / proofs

| Proof | Result |
|---|---|
| Production health | PASS (`200` before/after/reapply; env binding match) |
| Existing outbound Wathefni/Postmark | PASS (resolve + Postmark `/server` 200) |
| Existing Postmark inbound | PASS (inbound enabled + durable ingress) |
| Missing settings → legacy Wathefni | PASS (`settings_rows=0`, resolve mode=wathefni) |
| Microsoft / company-domain visible but not activatable | PASS (`microsoft_not_available`, activation blocked) |
| Tenant isolation + permission gates | PASS (17 qualification tests + prove script) |
| Calendar/Teams interview path unchanged | PASS (calendar module env + no mail_send import) |
| Dual-send skip after successful calendar invite | PASS (pure semantics + source gates) |
| Rollback verified (true pre-hybrid) | PASS (`true_pre` app SHA `2e06d917…` restored; modules removed; health 200; then re-applied) |

Unit/qualification on prod: `tenant_email_authority Phase 1 PASS`, `17 tests OK`.

## Rollback

- True pre-hybrid backup: `/opt/wathefni/backups/production-pre-hybrid-email-phase1-20260731T010337Z`
- Restore SHA matched: `2e06d91708fbb31c0de1d70c6151cb77b1d51407e46998efc93cf395341499fc` (`app.py`)
- Modules confirmed absent after rollback; Phase 1 dark re-applied and re-proved

## Screenshots

- `settings-email-sending-en-desktop.png` — Settings → Communications → Email sending (EN)
- `settings-email-sending-ar-mobile.png` — Communications AR/RTL mobile

(Same Settings UX content shipped in production dashboard bundle `SettingsPage-Dp-jwQs7.js`.)

## Explicitly not done (by design)

- Microsoft outbound not enabled
- No customer-specific sender configuration
- No `Mail.Send` provision/grant
- No Calendar/Teams permission changes
