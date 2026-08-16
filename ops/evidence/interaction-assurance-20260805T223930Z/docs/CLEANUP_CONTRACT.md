# Cleanup contract — interaction assurance fixtures

Version: `iax-cleanup-1.0.0`

## Rules

1. Scope only by `company_code` + markers (`IAX`, `IAX-SYNTH|`) + phone prefixes (`965542`) + optional `iax_synth` JSON flag.
2. Idempotent: pre-clean and post-clean are both safe.
3. Children → parents (tasks/notifications → leave/attendance synthetic rows → employees).
4. Never delete non-marker / real rows; never touch protected production allowlists.
5. Append-only **admin audit** rows may remain by design; operational leftovers must be **0**.
6. Deploy `ROLLBACK.sh` restores code/flags; it is not a substitute for data cleanup.

## Post-canary asserts

- Leftover IAX employees == 0  
- Leftover IAX-tagged open tasks == 0 (or explicitly documented retention)  
- Four real / demo seed invariants unchanged when running on WATHEFNI  

## Library

Shared create/cleanup: `wathefni-orchestrator/interaction_assurance_fixtures.py`
