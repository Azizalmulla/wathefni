# Release gate — interaction assurance

## Hard fail (blocks release / build)

1. **Static dead-control inventory** — dashboard `prebuild` (`ops/full-web-e2e/run-static-control-inventory.cjs`) finds any control with no handler/route/native/disabled binding.
2. **Confirmed P0/P1 regressions** — `ops/full-web-e2e/run-interaction-assurance-release-gate.py` sees matrix rows with:
   - `severity` in `{P0,P1}` and
   - `status` in `{broken, dead, permission mismatch}`  
   (not `unproven`, not P2).

## Soft / tracked (do not block product development)

- Remaining P1 `unproven` destructive properties (progressive synthetic program)
- P2 raw mutation error contracts (module waves)
- Incomplete synthetic batch coverage

## Usage

```bash
# Against the closed audit stamp (or a refreshed matrix path):
INTERACTION_AUDIT_MATRIX=ops/evidence/full-interaction-dead-control-audit-20260805T195406Z/findings/interaction-control-matrix.json \
  python3 ops/full-web-e2e/run-interaction-assurance-release-gate.py
```

Exit `0` = no confirmed P0/P1 regressions. Exit `1` = block release.
