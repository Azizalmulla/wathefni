# Pricing Go-Live Checklist

Use this only after the release-candidate suite is green. This checklist is for the later production cutover window, not normal development.

## Go / No-Go Gate

All of the following should be true before go-live:

- `npm test --prefix /Users/azizalmulla/Desktop/claw/delivery/plugins/riders-tools` passed on the candidate commit
- `RIDERS_PRICING_SOURCE_MODE=published_preferred`
- `RIDERS_PRICING_RESOLVER_OVERLAY_PATH` points to the deployed overlay file
- `admin_pricing_source_status` reports:
  - `active_source = published_snapshot`
  - `pricing_resolver_overlay.state = active`
- `admin_validate_pricing_resolver_overlay` returns `ok`

If any of those fail, the answer is `no-go`.

## Production Preflight

- Real Riders API credentials are loaded from secure storage
- Gateway token is rotated from the placeholder
- Delivery WhatsApp account is separate from the recruiter environment
- Dedicated production Google Sheets credentials are ready, or sheet publish is intentionally quarantined from production use
- Monitoring/log access is available during the cutover window

## Deploy Window

1. Run `delivery/scripts/deploy.sh`
2. Confirm the deploy created a fresh backup directory under `/opt/riders-delivery/backups/<timestamp>/`
3. Restart confirmation shows `riders-delivery` active
4. Run:
   - `admin_pricing_source_status`
   - `admin_validate_pricing_resolver_overlay`

## Live Verification

Run a focused post-deploy smoke with the admin/customer path:

- grouped route: `جنوب سعد العبدالله`
- ambiguity: `الخيران`
- ambiguity: `الوفرة`
- ambiguity: `سعد العبدالله`
- grouped route: `جنوب صباح الأحمد`
- direct alias: `علي صباح`

Expected outcomes:

- grouped routes quote without guessing numbered sectors
- ambiguous routes ask for clarification instead of collapsing to one area
- direct aliases resolve to the intended canonical area

## Rollback Triggers

Roll back immediately if any of the following occur:

- overlay status becomes `missing` or `invalid`
- `active_source` is not `published_snapshot`
- customer pricing starts collapsing known ambiguous areas without clarification
- live deploy produces obviously wrong route pricing for validated smoke routes
- customer booking flow fails because the deployed pricing config is missing the overlay path

## Rollback Procedure

1. Restore the previous `pricing.published.json` from the latest backup
2. Restore the previous `pricing.resolver.overlay.json` from the latest backup
3. Restart `riders-delivery`
4. Re-run:
   - `admin_pricing_source_status`
   - one focused `get_price` smoke on a known-good route

Do not continue the cutover until the rollback state is confirmed healthy.
