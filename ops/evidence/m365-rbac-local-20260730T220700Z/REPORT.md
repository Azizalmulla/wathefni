# Microsoft Exchange RBACfA — local interactive-browser assignment

**Stamp:** `20260730T220700Z`  
**Method:** Mac `Connect-ExchangeOnline` interactive browser (not device code)  
**Signed-in:** `ABDULAZIZALMULLA@wathefni.onmicrosoft.com`  
**Tenant:** `ffd171d7-94a7-41a2-a38a-b9bc3ba4a082` (`wathefni.onmicrosoft.com`)

## Admin probe — PASS

| Check | Result |
|---|---|
| Exchange Online connect | **PASS** |
| `IsDehydrated` | **False** |
| `RemotePowerShellEnabled` | **True** |
| Recipient | `UserMailbox` |
| `Get-ManagementRoleAssignment` (role read) | **PASS** |

## Assignment — PASS

```powershell
New-ManagementRoleAssignment `
  -App 46f5549d-4382-48fa-9c20-aff2f13451d5 `
  -Role "Application Calendars.ReadWrite" `
  -RecipientAdministrativeUnitScope 9d4e6a0e-47af-4603-a8f2-532e45911d40
```

Created UTC: `2026-07-30T22:12:23Z`  
Name: `Application Calendars.ReadWrite-46f5549d-4382-48fa-9c20-aff2f134`  
`CustomResourceScope` / AU: `9d4e6a0e-47af-4603-a8f2-532e45911d40`  
`RecipientWriteScope`: `AdministrativeUnit`

## Authorization verify — PASS

| Resource | `Application Calendars.ReadWrite` `InScope` |
|---|---|
| `ABDULAZIZALMULLA@wathefni.onmicrosoft.com` (in AU) | **True** |
| `wathefni-rbac-deny-probe@wathefni.onmicrosoft.com` (outside AU) | **False** |

AU membership: evidence user `dcb6b7dd-8509-4a20-8069-ec0de9445dd7` **in** `Wathefni-Calendar-Evidence`.

## Graph live create (post-assign)

| Time (UTC) | Result |
|---|---|
| ~22:12–22:15 | **403** `ErrorAccessDenied` (plain + Teams) — cert token mint PASS; token `roles` empty (expected for RBACfA-only) |
| Ongoing | Polling Graph create for RBACfA propagation (Microsoft can take tens of minutes) |

**Not yet declared PASS:** production `prove-m365-live-calendar.py` and full Teams interview matrix remain blocked until Graph create succeeds.

## Artifacts

- `probe.log`, `assign.log`, `reverify.log`, `au-members.log`, `au-and-deny.log`, `exo-deep-check.log`
- `rbac-assign-result.json`
