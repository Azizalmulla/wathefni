# Employee Mobile — Activation Path Fix (Kuwait local phone)

**Stamp:** `20260805T033940Z`  
**Root cause:** App UI shows a fixed `+965` chip and sends **local 8 digits** (`99338566`). Invites/employees store `96599338566`. Activate looked up invites with exact `phone=%s`, so the invite was never found → generic client error.

## Fix (production orchestrator)

- Invite lookup: `phone = ANY(aliases)` (8 ↔ 965…)
- Code hash verified against **invite stored phone**
- Employee lock by `employee_key` (not exact request phone)
- Code digit-normalized for spaced OTP entry
- Caddy `/app*` → `:8010` (already in place)

## Proof

Public edge `POST https://api.wathefni.ai/app/auth/activate` with phone `99338566` → **200**, then `/app/me` → **200** for `WATHEFNI-96599338566`.

## Fresh unused code for Aziz

| Field | Value |
|---|---|
| App phone field (with +965 chip) | `99338566` |
| Also accepted | `96599338566`, `+96599338566` |
| Activation code | `221913` |
| Expires | ~2026-08-06 03:39 UTC |
| Employee | `WATHEFNI-96599338566` · WATHEFNI |
| Allowlist | Talal + Aziz QA (unchanged) |
