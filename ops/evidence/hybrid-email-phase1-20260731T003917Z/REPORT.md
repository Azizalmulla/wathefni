# Hybrid email Phase 1 — local evidence

**Stamp:** `20260731T003917Z`  
**Deploy:** none (explicitly not production)

## Reduced Phase 1 plan (approved slice)

Preserve current production defaults:

- Postmark inbound CV/document ingestion unchanged
- Wathefni/Postmark outbound default
- Microsoft Calendar/Teams unchanged

Ship smallest useful slice:

1. Tenant outbound sender choice (Wathefni | Microsoft mailbox | company domain)
2. Backend/admin operational mailboxes (`careers@`, `hr@`, `onboarding@`, `payroll@`, `compliance@`)
3. Separate Microsoft mail SP client (`Mail.Send` only, dark until env present)
4. Company-domain Postmark verification fail-closed for unverified From
5. Dual-send interview guard + simple Settings toggle
6. Delivery audit columns
7. Simple Settings → Communications UX
8. Setup-console admin controls

Out of Phase 1: Microsoft inbound, Google placeholders, module-routing UI, prod deploy.

## What landed (in-repo)

| Area | Path |
|---|---|
| Authority | `wathefni-orchestrator/tenant_email_authority.py` |
| MS send client | `wathefni-orchestrator/microsoft_mail_send.py` |
| Schema + send wiring + APIs | `wathefni-orchestrator/app.py` |
| Dual-send explicit path | `wathefni-orchestrator/action_registry.py` |
| Company Settings UX | `apps/wathefni-dashboard/src/pages/SettingsPage.tsx` |
| API/types | `apps/wathefni-dashboard/src/lib/api.ts`, `types.ts` |
| Admin console | `apps/wathefni-dashboard/src/setup-console/EmailAdminPanel.tsx` + Company Control Integrations |
| Tests | `wathefni-orchestrator/test_tenant_email_authority.py` |

## Defaults / compatibility

- Missing `company_email_settings` ⇒ outbound `wathefni`
- Unready Microsoft / company-domain selection falls back to Wathefni on actual send
- Never spoofs unverified company From for company-domain provider path
- Calendar/Teams SP untouched; mail SP uses `WATHEFNI_M365_MAIL_*` and refuses calendar client id reuse
- Graph success recorded as accepted (`provider_accept_status=accepted`), not confirmed delivery

## Settings UX (company users)

**Communications**

- **Email sending** — current sender, three choices, display name, Reply-To, status Ready/Setup required/Verifying/Error, primary Connect/Verify/Test, toggle “Also send an email with calendar invitations”
- **Email & document intake** — existing Wathefni intake address + forward instructions only

No SP / RBAC / capability IDs / tokens exposed.

## Admin console

Setup Console → company → Integrations → Email sending (admin):

- seed operational mailboxes
- approve / disable / probe
- domain verify/refresh
- force Wathefni fallback

## Test evidence

```text
$ python3 test_tenant_email_authority.py
tenant_email_authority Phase 1 PASS
```

Covers: defaults, unverified From refuse, Microsoft activation matrix, dual-send skip, Postmark status mapping, inbound regression (durable ingress not rewritten).

## Not done / blocked on approval

- Production schema apply / deploy
- Provisioning real Microsoft mail SP + Exchange RBAC scopes in customer tenants
- Live Microsoft send probe against evidence mailbox
- Microsoft inbound ingestion (explicitly deferred)
