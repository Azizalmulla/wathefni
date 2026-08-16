# Pre-Hiring Interviews — Staging Green (Google CLI fix)

**Status:** staging-green  
**Production:** **not promoted / untouched**  
**Source of truth:** `/tmp/wathefni-c3-local` (surgical Google CLI fix only)  
**Prior green:** `4ffa87f435b613cc3ac1ed7cdf3c17fe3b9ec77c267cddf8ed596ccd90739a3a`  
**This green:** `c434d4b2076ccf22e4808b3f8739d48ba9b11f22ee05628915e8026e5f902cb9`  
**Delivery:** `WATHEFNI_DELIVERY_MODE=dry_run`  
**Stop:** do **not** run `ops/deploy.sh production` until owner approval.

---

## Verdict

Live Google Calendar create → reschedule → cancel is green against staging `gog` v0.12.0. Only `_google_update` / `_google_delete` argv shapes changed. Wathefni remains canonical. Synthetic fixtures cleaned to zero residue. Frozen-module regressions pass. **Stop for owner approval before production.**

---

## Exact code delta (Interviews only)

File: `interview_service.py`  
SHA256: `8f10e8f741436b5edc22ab0ea14ce1a7c1d539985e5502f00086d84e1c0b01b6`

1. **`_google_update`** — never append `--with-meet` (unsupported on `gog calendar update`); keep same `event_id` so Meet/conference on the existing event is preserved.
2. **`_google_delete`** — add `--force` for non-interactive delete (`gog` refuses without it).

No schema, scheduling authority, UX, Ranking, Reports, Assistant, or Assessments changes.

Pre-fix backup: `/opt/wathefni/backups/staging-pre-interviews-gcal-cli-20260724T211151Z`

---

## Identifiers

| Item | Value |
|---|---|
| Staging artifact SHA | `c434d4b2076ccf22e4808b3f8739d48ba9b11f22ee05628915e8026e5f902cb9` |
| Staging-green file | `/opt/wathefni/staging/last-green.sha256` |
| Host | `root@76.13.63.68` |
| Backend | `wathefni-orchestrator-staging.service` · `127.0.0.1:8011` |
| Database | `wathefni_staging` |
| Google account | `azizalmulla16@gmail.com` |
| Live soak tenant | **`INTVGCAL`** · marker `interviews-live-gcal-soak-v1` |
| Matrix tenants | **`INTVLIVE`** / **`INTVVID`** |

---

## Local focused tests

`smoke-test-interviews-gcal-cli.py` — **5/5 PASS**

- update omits `--with-meet`, same event id
- update fallback also omits `--with-meet`
- delete includes `--force`
- delete fallback includes `--force`
- create still supports `--with-meet`

`smoke-test-interviews-remediation-unit.py` — **9/9 PASS**

---

## Live Google Calendar soak

Evidence: `ops/interviews/interviews-live-gcal-soak-20260724T211301Z.json`  
Verdict: **PASS · 19/19**

| Gate | Result |
|---|---|
| Create one Google event | PASS `bpboc5dt8cn4mc08mbmp7ljuso` |
| Candidate + panel attendees | PASS |
| Meet link present | PASS `https://meet.google.com/tur-zysu-yoe` |
| Wathefni canonical after create | PASS (`synced`) |
| Reschedule same event id + synced | PASS |
| Google start updated in place | PASS `10:00+03` → `12:00+03` |
| No duplicate active events | PASS |
| Cancel Wathefni + provider synced | PASS |
| Google event status cancelled | PASS |
| No stale active Meet/event | PASS |
| Cleanup zero DB residue | PASS |
| Cleanup zero Google residue | PASS |

---

## Interviews matrix (includes live Google path)

Evidence: `ops/interviews/interviews-staging-matrix-20260724T211759Z.json`  
**45/45 PASS**, including:

- `google_connected_creates_one_event` → `aoap56q7gftcou0fqovpt9j8ig` synced
- `google_reschedule_same_event_no_duplicate` → same id, synced
- `google_cancel_syncs_without_invalidating_history` → synced
- cleanup zero residue

---

## Frozen-module regressions

| Suite | Result |
|---|---|
| Staging smoke | **PASS** (`ALL STAGING SMOKE CHECKS PASSED`) |
| Candidates C3 schema | **18/18** |
| Candidates C3 matrix | **49/49** |
| Ranking R0–R3 | **57/57** |
| Ranking presentation | **213/213** |
| Reports V1 | **80/80** |
| Assistant A0–A3 | **79/79** |
| Assessments Tenant ON/OFF | **35/35** |
| Interviews matrix | **45/45** |
| Live GCal soak | **19/19** |
| Production untouched | **PASS** (`interview_service.py` absent on prod; prod `app.py` `30d8fd13…`) |

---

## Residuals

None for Google OAuth or Calendar sync on this run. Prior `invalid_grant` residual is cleared by re-auth + this CLI fix.

---

## Owner UX / next step

1. Staging is green at artifact `c434d4b2…`.
2. Search markers **`INTVGCAL`**, **`INTVLIVE`**, **`INTVVID`** — expect no residue.
3. **Do not promote to production** until explicit owner approval.
