# Release gate — mobile action authority (`34f8b38`)

## Staging

- **staging-green artifact SHA:** `7f7792bf87e23c6e4bd544d456499f43749c20bc706db09545f0ca5bff1ab06d`
- **deployed source commit:** `34f8b38a93e15f3a23740d13048f579875a3ef90`
- **deploy result:** `ops/deploy.sh staging` → **Staging deploy OK** / `ALL STAGING SMOKE CHECKS PASSED`
- **smoke totals:** suite summaries **1545 passed, 0 failed** across 55 suites; dashboard vitest **29**; post-green authority smoke **55/55**; authenticated native proof **36/36**
- **outbound_delivery note:** commit `34f8b38` app.py already called pagination helpers missing from that commit’s outbound module; release tree includes a **pagination-only** outbound patch (no push / app_activation / leave product changes). Authority/mobile files match `34f8b38` byte-for-byte.

## Production

- **artifact SHA (identical to staging-green):** `7f7792bf87e23c6e4bd544d456499f43749c20bc706db09545f0ca5bff1ab06d`
- **flag state:** `WATHEFNI_CANONICAL_LIFECYCLE=true` (drop-in already present)
- **backup:** daily `20260718T001701Z`
- **rollback reference:** `/opt/wathefni/backups/predeploy-20260718T001709Z` (also in `/opt/wathefni/backups/.last-predeploy`)
- **deploy result:** `Production deploy OK` + public-route guard passed
- **prod smokes:** authority **55/55**; canonical lifecycle prod **21/21**; mobile authority prod proof **36/36**
- **real data:** WATHEFNI application/interview/employee/outbound/decision counters unchanged; synthetic companies fully removed

## Rollback

`ops/deploy.sh rollback` restores `/opt/wathefni/backups/predeploy-20260718T001709Z`.
