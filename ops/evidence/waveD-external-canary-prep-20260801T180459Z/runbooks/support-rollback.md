# Support & rollback procedure (forwarding-only canary)

## Emergency tenant kill switch (fastest, tenant-scoped)

Owner/admin with inbound plan permissions:

```http
PUT /dashboard/prehire/integrations/inbound-plan
{ "kill_switch": true }
```

Effect: new durable receives for that tenant enter `waiting_budget` / `tenant_kill_switch` (never-reject semantics). Existing Held items remain for review.

Clear when safe:

```http
PUT /dashboard/prehire/integrations/inbound-plan
{ "kill_switch": false }
```

## Soft disable (customer self-serve)

1. Settings → Email & document intake → **Disable** / **Rotate** intake address  
2. Optional: set `inbound_forwarding_enabled=false` on company settings  
3. Customer removes/pauses their mail forward rule

## Hard revoke (platform — external spillover stop)

1. Kill switch on for `<COMPANY_CODE>`  
2. Disable all active intake addresses for that company  
3. Revert allowlist to `WATHEFNI` only (see `artifacts/allowlist-change.DRAFT.conf`)  
4. `systemctl daemon-reload && systemctl restart wathefni-orchestrator.service`  
5. Confirm health 200 and allowlist env  
6. Confirm `WATHEFNI_MAILBOX_SYNC=off` unchanged  
7. Notify customer; leave Held apps for export/cleanup per support process

## Global brakes (last resort — affects WATHEFNI too)

- `WATHEFNI_INBOUND_EMAIL=off` (global inbound kill)  
- Pause `wathefni-inbound-intake-worker.timer` only with explicit ops approval (stops processing for all tenants)

Prefer tenant kill switch + allowlist revoke over global off.

## Support playbooks

| Symptom | Action |
|---|---|
| No mail arriving | Check customer forward; intake address status; allowlist; Postmark env pin |
| Held backlog growing | Coach HR on assign/admit; check identity warnings; do not auto-admit |
| `dead_letter` rising | Check ClamAV/OCR; replay outage jobs if scanner restored; soft-fail extraction should not loop forever |
| Malware hits | Quarantine already holds; do not release; notify customer |
| Quota waiting | Soft-warn first; raise plan or short burst override; never hard-reject |
| Suspected cross-tenant | Stop canary immediately; verify `company_code` on submissions |

## Rollback verification checklist

- [ ] Kill switch false or intentional  
- [ ] Allowlist = `WATHEFNI` (if revoked)  
- [ ] Canary intakes disabled  
- [ ] Mailbox sync still `off`  
- [ ] Orch/dash health 200  
- [ ] Intake worker timer active  
- [ ] No unexpected open jobs for canary company  
