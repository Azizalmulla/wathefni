# Hybrid Email — Microsoft outbound evidence (PARTIAL PASS)

**Stamp:** `20260731T014123Z`  
**Verdict:** **PARTIAL PASS** — setup + evidence send green; live Graph outside-scope deny still pending propagation  
**Commit (Phase 1 source):** `cf26d59512a22a7634eb4edd28b4425ec1624405`

## Preserved state (no further RBAC changes)

| Item | Value |
|---|---|
| Mail SP app id | `8994e095-0605-4baa-86c0-54185c95b496` |
| Mail SP object id | `a4ebfc44-a55d-4e50-a364-978f55c1d35c` |
| Calendar SP (unchanged) | `16f7135a-b7e8-4ac8-adfe-2d2b13de3131` |
| Graph permission | **Mail.Send only** (no Mail.Read / Mail.ReadWrite) |
| Exchange role | `Application Mail.Send` |
| AU scope | `Wathefni-Mail-Evidence` / `d3302de0-0dcc-4169-8937-17f440410a7b` |
| Evidence mailbox | `ABDULAZIZALMULLA@wathefni.onmicrosoft.com` |
| Outside-scope mailbox | `wathefni-rbac-deny-probe@wathefni.onmicrosoft.com` |
| AAP | RestrictAccess to `Wathefni-Mail-Evidence-Scope` (Test: Granted / Denied) |
| Evidence tenant mode now | **wathefni** (forced; Microsoft not left active) |
| Customer tenants | no branded modes |
| Health | 200 |

## Matrix status at abort

| Proof | Result |
|---|---|
| Separate mail-SP token mint | PASS (`roles: Mail.Send`) |
| Calendar SP cannot send mail | PASS (403) |
| Email SP cannot create calendar event | PASS (403) |
| Approved mailbox send | PASS (HTTP 202, `accepted_by_provider`) |
| Dispatch records `accepted_by_provider` | PASS |
| EXO `Test-ServicePrincipalAuthorization` deny InScope=false | PASS |
| AAP Test deny = Denied | PASS |
| Live Graph outside-scope `sendMail` deny | **FAIL / pending** (still HTTP 202) |
| Sent Items / Reply-To companion | not completed (blocked on deny) |
| Switch back to Wathefni | PASS |
| Mail env rollback script | present at `/opt/wathefni/backups/ROLLBACK-m365-mail-outbound.sh` |

## Follow-up (scheduled)

One controlled outside-scope `sendMail` probe at **~05:40 Asia/Kuwait**.  
- If Graph denies → minimal allow/deny matrix → upgrade to PASS  
- If still 202 → stop; report propagation still pending  
- No repeated emails; no RBAC changes

## Artifacts

- `mail-sp/` — Entra app, permissions, RBAC, AAP evidence  
- `remote/` — earlier matrix / deny-poll logs  
- `prod-snapshot.txt` — current prod dark-for-customers state  
