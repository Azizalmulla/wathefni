# Civil ID dual-side — qualification

**Stamp:** `20260806T014717Z`  
**Status:** Implemented behind flags · local smoke PASS · live disposable-canary prove pending deploy

| Check | Result |
|---|---|
| Draft attempt + parts schema | Implemented |
| Pair gate (incomplete / dup / mismatch / unknown soft) | Smoke PASS |
| Same-version promote to HR | Implemented |
| Legacy accepted projection | Smoke PASS (no upload_front) |
| Disposable canary ops script | Ready |
| Aziz accepted Civil ID mutation | Forbidden by design (accepted gate + canary isolation) |
| DocVal HARD | Remains off |
| Native scanner | Not built |

**Blockers to GA:** live canary prove on prod · soak · owner decision to enable dual-side for real `civil_id` replacement only after prove.
