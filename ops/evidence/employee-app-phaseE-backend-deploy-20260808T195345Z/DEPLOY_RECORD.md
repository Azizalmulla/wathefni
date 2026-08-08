# Employee App Phase E — backend production deploy

Deployed 2026-08-08T19:53:45Z to `root@76.13.63.68`, service
`wathefni-orchestrator.service`.

| Field | Value |
| --- | --- |
| Source commit | `c80900c` (`app.py` byte-identical to the committed file) |
| Artifact sha256 | `144a608f6fd3297d89b203206570c245b0bd2db0c137375a54223a8985ecfce8` |
| Previous sha256 | `6dee3d6c666eed88ae3a6bbfa032a7f387b8f26cf3cae5646238855e570d3219` |
| Deploy stamp | `20260808T195345Z` |
| Backup | `/opt/wathefni/backups/production-pre-employee-app-phaseE-20260808T195345Z` |
| Rollback | `<backup>/ROLLBACK.sh` |
| Files changed | `wathefni-orchestrator/app.py` only |

The applied diff was 128 lines across the Phase E hunks and nothing else, confirmed
on the server immediately before the copy (`diff` of the running file against the
uploaded artifact). Post-deploy sha matches the uploaded artifact exactly.

Rollback readiness: `app.py.pre` was proven byte-identical to the file that was
running (`diff -q`), `PRE_SHA256.txt` records its digest, and `ROLLBACK.sh` passes
`bash -n`. The rollback was **not** executed, so restore-and-reapply was not exercised
end to end; the backup content and the script are verified, the cycle is not.

## Verification

### Route is live and gated

`/app/leave/duration` returned **404 before** the deploy and **401 after**, both on
`127.0.0.1:8010` and through the public edge:

```
https://api.wathefni.ai/app/leave/duration?start_date=2026-08-10&end_date=2026-08-12
401 {"detail":{"error":"app_auth_failed","message":"Please sign in again."}}
```

401 rather than 404 is the point: the route exists and the employee auth dependency
is wired in front of it.

### No unrelated regression

Twenty parameterless GET routes spanning `/health`, `/ready`, `/dashboard/*`,
`/app/*` and `/orchestrator/*` were probed before and after. `routes-before.txt` and
`routes-after.txt` are identical — 200/200 for health and ready, 401 for all
eighteen authenticated routes. Health returned 200 after restart and the service is
`active`.

### Behaviour against real canary data

`runtime-verification.txt` records handlers called directly under the live service
environment with a faithfully reconstructed employee context. Read-only; nothing
written.

Leave duration, Thu 2026-08-13 → Mon 2026-08-17, for both canary employees:

```
calendar_days=5  chargeable_days=3.0  weekend_days=["fri","sat"]
excludes_public_holidays=true  basis=working_days
```

The weekend is excluded, so "You're requesting 3 days" is what the employee will see
for that range rather than a naive 5. A reversed range returns
`available:false, reason:"invalid_range"` instead of raising, so the client abstains
rather than inventing a number.

Home document-expiry detail, from canonical compliance rows:

- Aziz — one renewal (`employment_contract`, `rejected_reupload`, **no expiry date**).
  Detail projects the label in both locales (`Employment contract` / `عقد العمل`)
  with `expiry_date: null`.
- Talal — five compliance rows, zero renewals, detail correctly `None`.

## Carry into physical QA

Neither canary employee currently has a document with a **dated** expiry. Aziz's only
renewal is a rejected re-upload with `expiry_date: null`, which by design falls back
to the generic document label. The "Civil ID expires in 18 days" copy is therefore
correct but **not observable on the canary device as data stands** — verifying it
visually needs a seeded document with a real future expiry date. Worth knowing before
someone looks for that string on Home and concludes it is broken.
