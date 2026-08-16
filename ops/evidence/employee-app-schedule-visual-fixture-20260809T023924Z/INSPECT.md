# Schedule visual redesign — populated canary fixture

Stamp: `20260809T023924Z`

## Purpose

Physical judgment of the Schedule visual redesign with **realistic populated data** (not empty states). Design is intentionally unchanged.

## Identity (synthetic only)

| Field | Value |
| --- | --- |
| Employee | Noura Almutairi |
| Key | `WATHEFNI-96550010001` |
| Phone | `96550010001` |
| Activation code | `703012` |
| Invite expires | `2026-08-10 02:40:02+00` (~24h) |
| Allowlist | Already on `WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST` |

**Aziz / Talal were not modified.** No production employee facts invented on canary identities.

## How to inspect on iPhone

1. Open the Employee App (current canary OTA is fine — no new JS deploy required for this fixture).
2. Sign out of Aziz (or Talal).
3. Activate with phone **`96550010001`** and code **`703012`**.
4. Set PIN if prompted · open **Schedule**.
5. Judge with the checklist below.
6. When done: sign out · reactivate Aziz with your usual invite/resend path if needed.
7. Ask for fixture cleanup when judgment is finished (`--cleanup`).

## Seeded `/app/workday` shape (verified)

| Surface | Content |
| --- | --- |
| Today | `09:00–17:00` · location **Salmiya Branch** · recorded **Present** · check-in ~09:02 Kuwait |
| Upcoming | 3 shifts: Aug 10 `10:00–18:00` HQ Floor 3 · Aug 12 `14:00–22:00` Airport Road · Aug 14 `08:30–12:30` Salmiya |
| Recent | Present · **Late (12 min)** · Absent · Present |
| Summary (30d) | present 3 · late 1 · absent 1 |

## Judgment checklist (no redesign in this stamp)

- [ ] Today feels premium with real shift + recorded attendance
- [ ] Planned/scheduled work color role (today entry uses `PastelCard tone="sky"`; theme currently maps `sky` → butter yellow — decide if blue is required)
- [ ] Upcoming is useful and not repetitive
- [ ] Present / Late / Absent pills feel balanced
- [ ] Page is not too colorful or card-heavy when full
- [ ] Hierarchy still feels clean with realistic data

## Cleanup

On production orchestrator:

```bash
cd /opt/wathefni/orchestrator
.venv/bin/python ops-seed-schedule-visual-fixture.py --cleanup
```

Deletes only rows tagged `metadata.fixture = schedule-visual-fixture` for `WATHEFNI-96550010001`.

## Script

`wathefni-orchestrator/ops-seed-schedule-visual-fixture.py`
