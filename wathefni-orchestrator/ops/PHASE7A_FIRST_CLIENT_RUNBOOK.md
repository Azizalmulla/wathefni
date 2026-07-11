# Phase 7A — First-client provisioning runbook

Operator guide for provisioning a company through Setup Console V2 + workspace boot,
without engineering hand-edits.

**Status:** Staging-proven first. Do **not** create a real production client until
separately approved after company lifecycle controls are live and staging-green.

## Preconditions

- `WATHEFNI_SETUP_CONSOLE_V2=on`
- `WATHEFNI_WORKSPACE_BOOT=on`
- Protected flags remain OFF:
  - `WATHEFNI_EMPLOYEE_APP=off`
  - `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
  - `WATHEFNI_ONBOARDING_SEED=off`
- Operator credentials configured (`WATHEFNI_SETUP_OPERATOR_CREDENTIALS` + allowlisted phone)
- Health `200` on the target environment
- Latest rollback / predeploy snapshot available for production changes

## Company lifecycle states

| State | Meaning |
|---|---|
| `active` | Normal access. Login, invite accept, bootstrap allowed. |
| `disabled` | Access blocked. Sessions revoked. Pending invites superseded. Data/modules preserved. |
| `archived` | Access blocked. Hidden from default active company list. Reversible via Reactivate. |

There is **no hard delete** in Phase 7A.

`WATHEFNI` cannot be disabled or archived through Setup Console automation.

## Operator steps (happy path)

1. Open `/setup-console` and connect with operator token + authorised phone.
2. Create company: code, display name, country, timezone, currency.
3. Confirm profile fields.
4. Select modules (mixed pre/post-hire as required).
   - Hard dependencies auto-expand (`assessments` / `video_interviews` require `pre_hiring`).
   - Do **not** enable `employee_app` for a first client unless separately approved.
5. Review channel policy (mark reviewed). Do not provision live company channel accounts while that flag is OFF.
6. Create Owner invite (name, email, optional phone).
7. Copy the invite link and share it securely out-of-band. The console does not send invitations.
8. Owner opens invite, sets password (≥8), accepts.
9. Owner logs in with company code + email + password.
10. Verify:
    - `/dashboard/bootstrap` returns `200`
    - default landing is correct (`overview` when `pre_hiring` is on)
    - Team route loads
    - Alerts & Delivery is visible when any suite module is enabled
    - selected Pre-Hiring / Post-Hire pages load
11. Confirm shared dashboard token and Owner session cannot access Setup Console.

## Disable / Reactivate / Archive

### Disable
Use when a tenant must stop immediately without data loss.

- Requires a reason.
- Revokes active sessions.
- Supersedes pending invites.
- Blocks login, invite accept, and bootstrap.
- Preserves company row, modules, users, and operational data.

### Reactivate
- Requires a reason.
- Restores `active`.
- Preserves modules/data.
- Does **not** restore old sessions. Owner must log in again.

### Archive
- Requires a reason.
- Blocks access like disable.
- Hides company from the default active Setup Console list.
- Still visible when “Show disabled and archived” is checked.
- Reversible via Reactivate. No hard delete.

## Staging dress rehearsal

Automated verifier:

```bash
# on VPS, against staging (:8011)
python3 /opt/wathefni/staging/orchestrator/ops/staging-phase7a-provisioning-verify.py
# or after ops sync:
python3 /opt/wathefni/orchestrator/ops/staging-phase7a-provisioning-verify.py
```

Tenant code: `P7ASTG01`

The verifier proves create → modules → Owner invite/accept/login → bootstrap/Team/Alerts →
access boundaries → disable → reactivate → archive, and refuses to touch `WATHEFNI`.

## Production first-client gate (not this phase)

Only after separate approval:

1. Confirm lifecycle controls are deployed and staging-green.
2. Confirm protected flags still OFF unless approved.
3. Create the real client company through Setup Console only.
4. Issue Owner invite securely.
5. Keep a written reason trail for any later disable/archive.
6. Do not create throwaway production companies.

## Rollback

| Problem | Action |
|---|---|
| Wrong modules | Re-save modules in Setup Console (omit unwanted keys). |
| Wrong Owner invite | Re-issue Owner invite (supersedes pending). |
| Tenant must stop | Disable with reason. |
| Tenant ready again | Reactivate with reason; Owner logs in fresh. |
| Tenant no longer needed | Archive with reason (reversible). |
| Bad code deploy | Use `ops/deploy.sh rollback` / predeploy snapshot. |
| Feature flag issue | Flip flag off via systemd drop-in and restart orchestrator. |

## Security notes

- Never log or paste invite tokens, passwords, or operator tokens into tickets/reports.
- Shared dashboard token must never unlock Setup Console.
- Do not disable/archive `WATHEFNI` without a separate explicit approval outside this runbook.
