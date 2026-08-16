# Employee App — Onboarding visual + interaction

**Stamp:** `20260809T045135Z`  
**Verdict:** **PASS** (canary OTA)

## Seeded account

| | |
|---|---|
| Employee | `WATHEFNI-9655237101` · `W2B-SYNTH\| Onboarding Visual` |
| Phone | `9655237101` |
| Activation code | `622949` (expires ~2026-08-10 04:53 UTC — re-run seed for a fresh code) |
| Seed | `wathefni-orchestrator/ops-seed-onboarding-visual-fixture.py` |
| Cleanup | `.venv/bin/python ops-seed-onboarding-visual-fixture.py --cleanup` |

### Fixture state (live `/app/onboarding`)

| Section | Items |
|---|---|
| Your actions | `civil_id` **replacement_required** (rejection reason), `personal_photo` pending, `bank_details` pending |
| Being reviewed | `passport` processing, `offer_letter` processing |
| Handled by others | `work_permit` blocked (explicitly assigned — Wave 2A visibility) |
| Completed | 7 accepted/waived incl. `employment_contract`, `residence`, acks |
| Progress | 1 / 4 required · completion `waiting_on_employee` |

Aziz / Talal untouched. Allowlist drop-in: `zzzzzzzzzzzzzzzzzzzzzzzzzzzz-onboarding-visual-canary.conf`.

## Visual changes

- One lilac progress `PastelCard` only (≤1 ambient surface)
- Cream ledger rows instead of stacked white / Pastel checklist cards
- **Your actions** strongest: ink/pink accent bar; pink life mark only on needs-correction
- **Being reviewed** / **Handled by others**: quieter cream rows + quiet ink status words
- **Completed**: quietest collapsed ledger
- Selective colour via `OnboardingLifeMark` — no status chip on every row
- No fake marketing copy; all labels from template / i18n / server rejection reason

## Interaction fixes

- Latest-wins document preview (`openGeneration` + cancel prior transfer)
- Soft invalidate after upload (`softRefreshOnboarding`) — no `await invalidate` before UI continues
- Bank CTA navigates immediately (`router.push('/bank')`)
- Scroll stays stable: soft refresh does not remount via blocking await; bank push keeps checklist mounted

## Authority preserved

- Wave 2A groups / completion contract / upload capability / bank `open_bank` gate unchanged
- EN/AR keys unchanged; RTL + Dynamic Type multipliers retained on ledger titles
- Density + capability gates GREEN; Auth Wave 2 dist markers GREEN

## OTA / rollback

| | |
|---|---|
| Branch | `canary` |
| Update group | `da7d44f0-69d2-4379-80a6-77ef7a85ee19` |
| iOS update | `019fe4df-63d2-70bd-82b2-8087adb7caef` |
| Android update | `019fe4df-63d2-7bfa-9bfa-43e676571a1a` |
| Rollback | previous canary `f226bdf5-d48e-49ef-b172-7c3672a0723e` (Auth Wave 2 restore) |
| Publish | `scripts/publish-canary-ota.sh` |

## Evidence

- `seed.json`
- `http-onboarding.json`
- `ota-publish.log`
- `zzzzzzzzzzzzzzzzzzzzzzzzzzzz-onboarding-visual-canary.conf`
- `STAMP.txt`
