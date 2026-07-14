# HR-1 — Staging Closure Evidence

**Status:** staging-green (backend-only)  
**Date:** 2026-07-14  
**Artifact:** `602f6eb53e2bdda9bdca55fd174b40b00e63a4a49ed81382bcc366497abc8674`

## Proof

| Check | Result |
| --- | --- |
| Staging deploy | OK (`ops/deploy.sh staging`) |
| Full staging smoke suite | ALL CHECKS PASSED |
| Focused smoke `smoke-test-hr1-operator-mobile.py` | **84/0** |
| Staging verifier `ops/hr1-staging-verify.py` | **70/0** |

### Verifier coverage

- Mobile login / refresh rotation / refresh replay / logout / logout-all
- Token hashes only (no raw tokens in DB)
- `/dashboard/mobile/me` backend_current + capability accuracy
- One-company binding (forged `X-Company-Code` rejected)
- Manager scope metadata + missing-scope fail-closed
- Grant revoke + module removal take effect on next request
- Employee token / browser session / legacy shared token rejected
- Company disable blocks login and sessions
- Browser `/dashboard/auth/login` unchanged
- Rate limiting

## Production

Not enabled. No production company configuration changes. No Wathefni HR frontend shipped.

## Next

Stop for review. Recommend **HR-2 — Wathefni HR Frontend Design and Initial Implementation** only after HR-1 review.
