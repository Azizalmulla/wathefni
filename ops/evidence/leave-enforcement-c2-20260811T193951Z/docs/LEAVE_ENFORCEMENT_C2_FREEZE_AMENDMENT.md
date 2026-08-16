# Leave Enforcement C2 — Freeze Amendment

**Status:** AMENDS `ops/LEAVE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` for Wave 2 **C2 only**  
**Charter:** `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`  
**Pass stamp:** `LEAVE_ENFORCEMENT_FULL_PASS`  
**Qualify:** `ops/qualify-leave-enforcement-c2-staging.sh`

## What changes

| Prior freeze | C2 amendment |
|---|---|
| Real balance enforcement NO-GO | Company-scoped `leave.enforced` via `leave_enforcement_c2` after **versioned pack attestation** |
| Global enforcement off forever | **Global** `WATHEFNI_LEAVE_ENFORCEMENT` stays **off** in systemd; empty `*_COMPANIES` = nobody |
| No workflow_approvals bind | Optional bind of `leave_request` subject; single-step remains when unbound/off |

## What does **not** change

1. Existing leave request SM + frozen UX unless a later surface amendment is explicit  
2. Append-only ledger as balance authority  
3. Self-approval bans  
4. Unpaid leave does not invent balances; payroll money remains NO-GO  
5. No hard dependency on Attendance or Payroll  
6. Assistant mutations remain OUT of Wave 2 MVP  

## Enablement sequence (canary only)

1. Bind KW pack  
2. `attest_company_policy_pack` (reviewed_by + reason + ref)  
3. Process-scoped `WATHEFNI_LEAVE_ENFORCEMENT=on` + company allowlist  
4. `enable_company_enforcement`  

## Rollback

```text
WATHEFNI_LEAVE_ENFORCEMENT=off
Clear WATHEFNI_LEAVE_ENFORCEMENT_COMPANIES
disable_company_enforcement(canary)
```

## Next

Stop for owner review. **Do not start C3 Shifts MSS** until `LEAVE_ENFORCEMENT_FULL_PASS` is accepted.
