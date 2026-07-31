# Hybrid email Phase 1 — qualification (fail-closed fallback)

**Stamp:** `20260731T005313Z`  
**Deploy / prod schema:** none

## Authority correction

Silent Wathefni fallback for explicit branded modes is **removed**.

| Case | Behavior |
|---|---|
| Missing settings / legacy tenants | Wathefni default (unchanged) |
| Explicit `wathefni` | Send through Wathefni |
| Activate Microsoft / company-domain | Blocked until fully ready (verified domain + From match; or approved mailbox + separate mail SP + successful probe) |
| Active branded provider unavailable | **Fail closed** by default |
| Optional `allow_wathefni_emergency_fallback` (default **false**) | When enabled and used: send via Wathefni, set `emergency_fallback_used`, `intended_mode`, `hr_notice` in delivery audit; surface notice to HR |
| Visible sender | Never silently changed; emergency path is explicit and recorded |

Graph success status is now `accepted_by_provider` (not delivered).

## Qualification proofs

| Proof | Result |
|---|---|
| Tenant A cannot see/select Tenant B mailbox/domain | PASS (`TenantIsolationTests`) |
| Unverified company From rejected | PASS |
| Microsoft rejected without approved+probed mailbox and mail SP | PASS |
| Calendar client id cannot mint mail token | PASS (`must_differ_from_calendar_sp`) |
| Graph accept stored as `accepted_by_provider` | PASS |
| Legacy defaults Wathefni | PASS |
| Dual-send skips only after successful calendar attendee invite | PASS |
| Explicit manual email not skipped | PASS |
| Failed calendar does not suppress transactional email | PASS |
| API routes gated (`settings.manage` / `superadmin_context`) | PASS |
| Public Settings projection has no SP/RBAC jargon | PASS |
| FE EN + AR/RTL Communications cards | PASS (3 vitest) |
| Inbound durable ingress not rewritten | PASS (source contract) |

## Test commands / artifacts

- `python3 test_tenant_email_authority.py` → `unit-authority.txt`
- `python3 -m unittest test_tenant_email_qualification.py -v` → `qualification-unittest.txt` (17 ok)
- `npm test -- --run src/pages/SettingsEmailSending.test.tsx` → `frontend-vitest.txt` (3 passed)
- `inbound-regression-source.txt`

## Screenshots

- `settings-email-sending-en-desktop.png` — desktop EN Email sending card
- `settings-email-sending-ar-mobile.png` — mobile AR/RTL Communications

## Still not done

- Production schema apply
- Production deploy
- Live Microsoft mail SP provision + Exchange RBAC evidence against customer/evidence tenant
