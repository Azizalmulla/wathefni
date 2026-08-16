# Pre-Hiring Interviews — Live Google Calendar Soak

**Date:** 2026-07-24  
**Artifact:** `4ffa87f435b613cc3ac1ed7cdf3c17fe3b9ec77c267cddf8ed596ccd90739a3a` (unchanged)  
**Verdict:** **FAIL_PRODUCT** — stop for owner approval; **do not promote**  
**Code:** not modified · **Production:** not touched

---

## What ran

1. Re-authenticated staging `gog` account `azizalmulla16@gmail.com` (remote OAuth step 1/2 + force consent).
2. Confirmed Calendar API works (`calendar calendars` OK).
3. Ran isolated live soak against frozen staging modules only:
   - Script: `/tmp/interviews-live-gcal-soak.py` (not part of artifact)
   - Tenant: **`INTVGCAL`** · marker `interviews-live-gcal-soak-v1`
   - Evidence: `ops/interviews/interviews-live-gcal-soak-20260724T210749Z.json`
   - Staging path: `/opt/wathefni/staging/orchestrator/ops/interviews/interviews-live-gcal-soak-20260724T210749Z.json`

---

## Gate summary

| Area | Result |
|---|---|
| Artifact SHA match | PASS |
| OAuth / Calendar list | PASS |
| Create → one Google event | PASS (`uidhi2fn8u6mftbpvfd65b40g4`) |
| Candidate + panel attendees | PASS |
| Meet link present | PASS (`https://meet.google.com/iri-utew-gny`) |
| Wathefni canonical after create | PASS (`scheduled`, `provider_key=google`, `synced`) |
| Reschedule updates same event | **FAIL** |
| Cancel removes/cancels Google event | **FAIL** |
| No duplicate after reschedule | PASS (event unchanged / stale) |
| Cleanup zero DB residue | PASS |
| Cleanup zero Google residue | PASS (forced cleanup after product cancel failed) |
| Overall | **14/19 PASS · FAIL_PRODUCT** |

---

## Exact product defects (frozen `interview_service.py`)

Against staging `gog` **v0.12.0**:

### 1. Reschedule / update — unsupported `--with-meet` on `calendar update`

Frozen `_google_update` always appends `--with-meet` when meeting type is Google Meet.

CLI probe:

```text
gog calendar update primary <eventId> ... --with-meet
→ rc=2  unknown flag --with-meet
```

Without `--with-meet`, the same update succeeds and moves the event in place.

Soak effect:

- Wathefni reschedule **succeeded** (`status=scheduled`, same `calendar_event_id`)
- `provider_sync_status=failed` · `provider_sync_error=calendar_update_failed`
- Google event start **unchanged** (stale)
- Wathefni remained canonical (`interview_valid: True`) — correct failure isolation, but sync incomplete

### 2. Cancel / delete — missing `--force` / `-y` for non-interactive delete

Frozen `_google_delete` runs:

```text
gog calendar delete primary <eventId> --send-updates all --no-input [--account ...]
```

CLI probe:

```text
→ rc=2  refusing to delete event ... without --force (non-interactive)
```

With `-y` / `--force`, delete succeeds.

Soak effect:

- Wathefni cancel **succeeded** (`status=cancelled`)
- Provider sync **failed** (`unexpected argument primary` / cancel failed path; underlying CLI refusal is `--force`)
- Google event remained **`confirmed`** until soak cleanup deleted it

---

## Proven good (live)

- OAuth re-auth restored staging Calendar access.
- Create path works end-to-end: one event, correct attendees, Meet link, Wathefni `synced`.
- Wathefni stays authoritative when Google update/cancel fails.
- Synthetic `INTVGCAL` cleanup left **zero** DB and Google residue.

---

## Non-goals / boundaries

- No Interviews code change
- No artifact rebuild
- No production promote
- Staging-green SHA still `4ffa87f4…`

---

## Owner decision

Live Calendar soak **does not clear** production promote.

Required before re-soak / promote consideration:

1. Fix `_google_update` to omit `--with-meet` (Meet already on event; create-only flag).
2. Fix `_google_delete` to pass `--force`/`-y` for non-interactive cancel.
3. Re-run this live soak to green.
4. Explicit owner approval for production.


---

## Follow-up (2026-07-24T21:13Z)

CLI mismatches fixed surgically in `interview_service.py`. Re-soak:

- Evidence: `ops/interviews/interviews-live-gcal-soak-20260724T211301Z.json`
- Verdict: **PASS 19/19**
- New staging-green artifact: `c434d4b2076ccf22e4808b3f8739d48ba9b11f22ee05628915e8026e5f902cb9`
- See `ops/PREHIRING_INTERVIEWS_STAGING_GREEN.md`
- **Still stop for owner approval before production.**
