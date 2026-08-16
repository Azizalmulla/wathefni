# Attendance Wave 2G — Production Dark Persistence

**Stamp:** `20260802T111431Z`  
**Host:** `root@76.13.63.68` · orchestrator `:8010` · DB `wathefni`  
**Evidence:** `ops/evidence/attendance-wave2g-dark-20260802T111431Z/`

## Verdicts (separate)

| Gate | Result |
|------|--------|
| **Production dark persistence** | **GO** |
| **HR capture-operations readiness** | **CONDITIONAL GO** (durable ops UI/API ready; ingest still off; lab/synthetic only) |
| **Customer read-only compatibility pilot** | **NO-GO** |
| **Real punch ingestion** | **NO-GO** |

Hard bans held: no customer device, no real punches, `CAPTURE_INGEST=off`, import off, QR/GPS/kiosk off, authority synthetic-only, freezes green.

## Preflight (before)

- `CAPTURE_STORE` **unset** → process-local memory (Wave 2E)
- Flags: `CAPTURE_OPS=on`, `CAPTURE_INGEST=off`, `IMPORT=off`, `AUTHORITY_SYNTHETIC_ONLY=on`
- Attendance rows: **42** / demo_seed **42** / four reals **4**
- Backup: `/opt/wathefni/backups/production-pre-attendance-wave2g-20260802T111431Z/` (+ tested `ROLLBACK.sh`)

## Deployed schema & flags (after)

**Store:** `WATHEFNI_ATTENDANCE_CAPTURE_STORE=postgres`  
**Ingest:** `off` · **Import:** `off` · **Synthetic-only:** `on`  
**Markers extended:** `ATTW2G`, `W2G-SYNTH|`

**Tables:** 13 `attendance_capture_*` + immutability triggers on audit + replay ledger.

**Key SHAs (final):**
- `attendance_capture_ops.py` → `0ac71abd7e21c151b88797f4b1b46b0ce57fee72fc78d9efcc44b707f2220a1e`
- `attendance_capture_postgres.py` → `910d5a3683ba47053114fb85bc22ced369710b37425462299241f213ef640172`

See `remote/flags/final-flags.txt`, `remote/verify/post-fix-shas.txt`.

## Proofs

| Proof | Result | Artifact |
|-------|--------|----------|
| Canary (synthetic) | **48/0** | `remote/canary/qualification.json` / `canary-after-redeploy.out` |
| HTTP host restart | **PASS** + **seed 200** (token arg bug fixed) | `remote/tests/restart-http-proof.out` |
| Checkpoint exactly-once | **PASS** | canary |
| Unknown mapping across restart | **PASS** | canary |
| Concurrent approve fail-closed | **PASS** | canary |
| Replay → Wave 1 exactly once | **PASS** | canary |
| Health/lag/offline history | **PASS** | canary |
| Tenancy / self / scope denials | **PASS** | canary |
| Secrets / leak scan | **PASS** | `remote/privacy/leak-scan.json`, local privacy scan |
| Authenticated EN/AR desktop+mobile UI | **PASS** | `screenshots/` (seed **200**, no fallback) |
| Rollback removes durable layer | **PASS** (`ROLLBACK_OK`, schema dropped, `CAPTURE_STORE` unset) | `remote/rollback/` |
| Redeploy succeeds | **PASS** | `remote/rollback/redeploy.out` + post-fix canary **48/0** |
| Capture tables → zero | **PASS** | `remote/cleanup/zero-tables*.out` |
| 42 demo + 4 reals untouched | **PASS** | canary pre/post + final cleanup |
| Freezes E360 / Onboarding | **57/0**, **54/0** | `tests/freeze-*.out` |

## Seed/helper 401 fix

Root cause: screenshot helper called `http(POST, path, {"tag": ...})` and passed the JSON body as the **Bearer token**. Fixed to `http(..., token, body)`. Qualification no longer depends on fallback rows (`SEED 200` on production).

## Remaining blockers

1. **Real capture channels still off** — device LAN, BioTime ingest, import, QR/GPS/kiosk remain disabled by design.
2. **Customer read-only compat pilot** not started (needs approved customer + read-only path + ops runbook).
3. **HR capture-ops** is durable and UI-ready, but operators should treat it as **dark/lab** until a dedicated pilot wave enables controlled remediations for a real tenant (still without ingest unless explicitly approved later).

## GO rationale (dark persistence)

Production now owns connector/health/checkpoint/remediation state in PostgreSQL with ingest remaining off, synthetic-only authority, rollback proven, cleanup to empty tables, and frozen modules unchanged. Safe to keep this dark persistence layer live.
