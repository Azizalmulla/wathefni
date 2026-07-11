# Phase 7B — One-employee production canary runbook

**Status:** Written for readiness only. **Do not activate** until separately approved.

Production `WATHEFNI_ONBOARDING_SEED` must remain **off** until that approval.

## Purpose

Prove checklist seeding on exactly one consenting/test employee without mass backfill
and without touching historical WATHEFNI employees unless explicitly approved.

## Preconditions

- Phase 7B staging verifier green
- `smoke-test-onboarding-seeding.py` green on staging
- Production health `200`
- Protected flags remain:
  - `WATHEFNI_EMPLOYEE_APP=off`
  - `WATHEFNI_COMPANY_CHANNEL_ACCOUNTS=off`
  - `WATHEFNI_ONBOARDING_SEED=off` (until the canary window below)
- Predeploy / config backup available
- Chosen canary company + employee agreed in writing
- Prefer a throwaway/test employee over a live historical WATHEFNI employee

## Canary employee selection

Use one of:

1. **Preferred:** a new roster employee created for the canary (opt-in `start_onboarding=true`)
2. **Alternate:** one existing employee with **zero** onboarding items and status suitable for start-onboarding

Do **not** run `/orchestrator/onboarding/seed-missing` against WATHEFNI (or any live company)
as part of the first canary.

## Activation steps (only after approval)

1. Confirm current prod flag is off:
   ```bash
   tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value wathefni-orchestrator.service)/environ \
     | grep WATHEFNI_ONBOARDING_SEED
   ```
2. Take a config backup / note latest predeploy snapshot.
3. Enable seed for the canary window only:
   ```bash
   # in the active setup-console-v2 (or dedicated) drop-in
   Environment=WATHEFNI_ONBOARDING_SEED=on
   systemctl daemon-reload
   systemctl restart wathefni-orchestrator.service
   ```
4. Verify health `200` and flag `on`.
5. Create **one** employee with Start Onboarding enabled, **or** run Start Onboarding for the one chosen empty employee.
6. Verify for that employee only:
   - checklist row count = Default Kuwait template size (currently 36)
   - required items only: `civil_id`, `personal_photo`, `employment_contract`, `bank_details`
   - re-run Start Onboarding → no duplicate rows
   - HR onboarding page shows pending required docs + non-required readiness tasks
7. Leave the seeded rows in place; do not delete as “cleanup” unless the employee is a disposable test record and cleanup is separately approved.

## Rollback (canary window)

```bash
Environment=WATHEFNI_ONBOARDING_SEED=off
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
```

Expected:

- Future seeding stops immediately
- Existing canary checklist rows remain intact
- No other employees are changed by rollback

## Pass / fail

**Pass:** one employee seeded correctly, idempotent re-run, no prod mass changes, rollback OFF works.

**Fail / abort:** unexpected duplicates, required HR/system nags, wrong company affected, or any WATHEFNI historical blast radius → flip flag OFF immediately and stop.

## Explicit non-goals for the first canary

- No mass `seed-missing` backfill
- No employee app enablement
- No company channel accounts
- No template editor work
- No compliance documents write-path reconciliation
