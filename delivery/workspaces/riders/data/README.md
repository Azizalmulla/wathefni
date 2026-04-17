# Riders Runtime Data

Files served or merged into the live Riders customer runtime.

## Live (served to customers)

- `pricing.published.json`
  Canonical published area catalog and price snapshot. Deployed by
  `scripts/deploy.sh` and served when `RIDERS_PRICING_SOURCE_MODE=published_preferred`.
  Backed up under `/opt/riders-delivery/backups/<timestamp>/` before overwrite.
- `pricing.resolver.overlay.json`
  Curated alias / ambiguity / pricing-group / geo-hint metadata. Merged on top
  of the published snapshot at runtime.
- `behavior-policy.published.json`
  Live customer-behavior policy (live instructions, reply corrections, flow
  rules, phrase guards). Managed through the `admin_*_behavior_*` tools.

## Fallback fixture (only when published mode is off)

- `pricing.json`
  Legacy static pricing fixture. Only loaded when
  `RIDERS_PRICING_SOURCE_MODE` is not `published_preferred` and
  `RIDERS_PRICING_PUBLISHED_PATH` is unset. Kept for local development and
  rollback testing. Do not treat as the source of truth.

## Test fixtures (not served at runtime)

- `pricing.resolver-fixture.json`
  Input for the local resolver smoke tests under
  `scripts/smoke-test-local-*-resolver.mjs`. Not loaded by the plugin.
