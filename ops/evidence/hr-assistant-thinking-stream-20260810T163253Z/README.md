# HR Assistant — Thinking + stream paint

Stamp: `20260810T163253Z`

## Ship
- API: `operator_mobile_assistant.py` (2-word paced deltas, `X-Accel-Buffering: no`)
- OTA group: `ac513bb4-2e70-491d-b0be-f27d1dfc5628` (runtime 0.3.0 / canary)
- iOS update: `019fec86-1ab6-7bed-91e8-e0252e3d07db`

## Fix
1. Mobile stream client uses `expo/fetch` (RN body streaming).
2. Waiting state is quiet pulsing **Thinking** / **يفكر** — no empty bordered bubble / `…`.
3. Reply paints progressively; non-stream fallback still reveals via client deltas.
4. Assistant message is plain text (no cheap surface card).

## Rollback
- OTA: prior `4dd457d0-dbb7-4d1a-8ff8-af60a05628e9`
- API: `/opt/wathefni/backups/hr-assistant-thinking-20260810T163253Z/operator_mobile_assistant.py`
