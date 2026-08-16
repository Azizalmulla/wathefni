# Hire-override audit harden — staging green

## Fix commit
`8ada28e7a14068252eaea3aaa455fdb771e5c9f4` — fail closed on hire override without durable audit

Harness follow-up: `test: fix Offer-1 owner override fixtures for durable audit proof`

## New staging-green SHA
`44c02407bdbf6484c9bb35ec44b0d841a0451cb52ee64261779ee67f2bbbd13c`

## Tests
- `smoke-test-offer-hire-override.py` — UUID actor, non-UUID subject, missing reason/permission/confirm, AI forbidden, audit insert failure fail-closed, stale stage, invalid stage, tenant mismatch, idempotent retry (exactly one audit), accepted-offer path unchanged, no hire when audit fails
- Staging smoke suite — ALL PASSED
- Owner-review — **49/49 PASS** including durable no-offer override audit

## Production recommendation
Ready to promote **this** staging-green SHA when approved. Do not promote older SHA `b99e800d…`. Production not touched in this pass.
