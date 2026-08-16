# Wathefni full-system E2E harness

Two repo-native commands:

```bash
./ops/test-smoke
./ops/test-release
```

No screenshot comparison, no video, no visual snapshots. The oracle is behavior and canonical domain state.

## Layers

| Layer | What | Tool |
|---|---|---|
| A. Structural/action sanity | Page destinations, dead "Not implemented", nav/capability | `ops/e2e/web-structural-sanity.py` |
| B. Action contracts | Authenticated HTTP: preconditions → action → backend truth | R9 attack + `ops/e2e/cross-surface-convergence.py` |
| C. Deep E2E | Maestro on a real simulator/device when the host is ready | `ops/mobile-e2e/run-release-gate.py` |

Mobile UI PASS is never invented. If Maestro/device is missing, the gate records BLOCKED.

## Suites

**FAST SMOKE** (`./ops/test-smoke`): R9/R2 unit, web structural, employee i18n, host readiness.

**RELEASE QUALIFICATION** (`./ops/test-release`): smoke + live R9 tenant attack + R10 measurement + R11 language + store build gate + staging cross-surface + clean Setup canary + physical host check + Maestro (if ready).

Physical PASS is never invented. Missing USB devices record `PHYSICAL_UNPROVEN`.

