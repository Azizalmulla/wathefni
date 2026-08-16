# 20260806T205803Z — Controlled broad rollout: Bank ESS + onboarding completion

Physical-device canary verification passed. This stamp expands the proven
contracts beyond Aziz/Talal canary while preserving canonical authority,
`pending_payroll → hr` ownership, and Talal as a permanent bank-negative control.

## Pre-rollout

| Gate | Result |
|---|---|
| Aziz synthetic payroll bank cleared | PASS — effective superseded, ESS profile soft-deleted, `bank_details=pending` for real submission (no invented IBAN) |
| Talal bank 403 | PASS — `bank_ess_not_allowlisted`, no `open_bank` |
| Rollback artifacts usable | PASS — backend/dashboard/OTA prior group present |

Aziz note: no non-synthetic bank details existed on file (Phase 2 + walkthrough
both used `KW30TEST…0000`). Clearing the fake payroll-effective row is the
correct replacement until Aziz submits real details through Bank ESS.

## Rollout scope

**Gradual, two stages (same stamp):**

| Stage | Bank surface | Bank real mutation | Employee app | Talal bank |
|---|---|---|---|---|
| 1 | synthetics + Aziz + Fouad + Noura + Mariam + Fahad + Dana | same real set | stage1 + Talal + synthetics | denied |
| 2 (final) | synthetics + 13 real WATHEFNI employees | 13 real | 17 keys (incl. Talal app-only) | denied |

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzzzzzzzzzzzzzzzzzz-bank-ess-broad-rollout.conf`  
Removed: temporary Aziz Phase 2 canary drop-in (folded into broad).

**Unchanged by design:**
- Auth Wave 2 (still blocked)
- Settings / Setup Console unrelated WIP
- `pending_payroll → hr` next-action ownership
- Onboarding completion contract (already company-wide for WATHEFNI)
- Dashboard + canary OTA clients already live from `20260806T200247Z`

## Smoke results

- Stage1 eligibility: `ELIGIBILITY_OK` (Aziz/Fouad/Noura enabled, Talal 403)
- Stage2 eligibility: `ELIGIBILITY_OK` (Brian enabled, Talal still 403)
- Consistency smoke: `SMOKE_OK` — 7/7 across Aziz, Talal, Fouad, Noura, Fahad  
  Queue / drawer / app / profile agree on state, progress, owner, next action  
  (unenriched queue rows for `not_started` employees noted, not counted as mismatch)
- Authority regression: `RECONCILE_AUTHORITY_OK` — 15/15

## Monitoring (15 min window)

- Orchestrator health: ok / active
- Journal ERROR/Traceback: 0
- Public edge: dashboard 200 · PostHire chunk 200 · healthz 200
- Reconcile idempotency probe: second call writes nothing
- Permission denials: expected Talal `bank_ess_not_allowlisted` only
- Duplicate / stale Apply signals: 0

## Rollback readiness

`./ROLLBACK.sh` restores pre-broad allowlists (reinstates Aziz temp canary drop-in).  
Client/OTA rollback remains `ops/evidence/onboarding-completion-reconcile-20260806T200247Z/ROLLBACK.sh`.

## Verdict

**`broad_rollout_go`** — Bank ESS eligibility expanded to all current real WATHEFNI
employees except Talal (negative control); onboarding completion remains the
canonical company-wide contract; surfaces agree; monitoring clean.

Auth Wave 2 remains **blocked**.
