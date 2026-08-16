# HR mobile VisQA fixtures

Production-safe synthetic fixtures for HR mobile **visual QA** (WATHEFNI).

## Marker

`hr_mobile_visqa_v1`

## Synthetic employees

| Key | Name | Used for |
| --- | --- | --- |
| `WATHEFNI-9655280101` | VISQA\| Sara Al-Mutairi | Document reviews, tasks, delivery alerts |
| `WATHEFNI-9655238102` | W2B-SYNTH\| VISQA Fahad Al-Sabah | Onboarding (HR-actionable) |
| `WATHEFNI-9655248103` | W2G-SYNTH\| VISQA Noura Hassan | Attendance + shift swap + tasks |

Aziz / Talal are never mutated.

## Provision / cleanup

```bash
# Seed (idempotent reset + insert + mobile API verify)
python3 ops/mobile-e2e/provision-hr-visqa-fixtures.py

# Cleanup only
python3 ops/mobile-e2e/provision-hr-visqa-fixtures.py --cleanup

# Re-verify mobile visibility
python3 ops/mobile-e2e/provision-hr-visqa-fixtures.py --verify-only
```

Fixture IDs are written to `~/.config/wathefni/visqa-fixtures.env` (gitignored).

## What you should see in the app

- **Document reviews** — 4 `needs_review` rows for Sara (Civil ID / Passport / Residency / Work permit); open any for detail + file
- **Onboarding** — Fahad with HR-review items (passport / offer / civil_id / residence)
- **HR Tasks** — 4 open `VISQA|` titles (delivery / activation / handoff / company-wide)
- **Delivery Alerts** — 3 VisQA messages (`needs_hr_action` / `failed` / `throttled`)
- **Attendance** — Today: 1 late; Unresolved: 3 exceptions (seeded inside the API’s first-31-day lookback window)
- **Shift swaps** — 1 requested VisQA swap

## Notes

- Real DB tables only — not `EXPO_PUBLIC_HR_*_DEMO`
- Attendance uses authority projections (synthetic `965524*` / `W2G-SYNTH|`) because WATHEFNI authority is SYNTHETIC_ONLY
- Verify authenticates as **Aziz owner** (`azizalmulla16@gmail.com`), not E2E HR. DB rows alone are not treated as seeded — mobile API VisQA hits must PASS.
- Bare `/attendance?status=exceptions` = **today only**. Unresolved in the app uses `start_date=today-92` / `end_date=today-1` (API then clamps to the first ~31 days of that window).
- Leave fixtures remain separate: `ops/mobile-e2e/provision-leave-fixture.py`
