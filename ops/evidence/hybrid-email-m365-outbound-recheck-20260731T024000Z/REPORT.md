# Microsoft outbound mail authority — COMPLETE

**Verdict:** **FULL PASS**  
**Stamp:** `20260731T024000Z`  
**Evidence:** this pack (recheck) supersedes the earlier PARTIAL pack for deny proof.

## Proof summary

| Check | Result |
|---|---|
| Outside-scope Graph send | **DENIED** HTTP 403 (`ErrorAccessDenied` / AppOnly AccessPolicy) |
| Approved evidence mailbox send | **ALLOWED** HTTP 202 `accepted_by_provider` |
| Tenant restored to Wathefni | **PASS** |
| Only evidence tenant toggled | **PASS** (`branded_remaining: 0`) |

Artifacts: `VERDICT.txt`, `minimal-matrix.json`, `outside-scope-probe.json`, `deny-ok.txt`

## Workstream status

**COMPLETE.** Do not reopen unless Microsoft outbound policy or mail SP scope changes.

Related earlier pack (historical PARTIAL before deny propagation):  
`ops/evidence/hybrid-email-m365-outbound-partial-20260731T014123Z/`
