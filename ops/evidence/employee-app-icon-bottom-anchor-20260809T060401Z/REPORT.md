# Employee App — Bottom-anchored icon + push sound test

**Stamp:** `20260809T060401Z`  
**Verdict:** **PASS** (icon assets) · push send **blocked until Aziz registers a token**

## Icon

Bottom-anchored Wathefni mark (flush to bottom edge, equal side padding, top breathing room).

| Asset | Path |
|---|---|
| iOS / general | `assets/icon.png` |
| Android adaptive | `assets/adaptive-icon.png` |

## Ship

| | |
|---|---|
| OTA | `c62ee5b8-9d61-4aaa-a197-3612f15c7e96` (also enables push registration) |
| iOS native | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/02779570-b7ed-46bc-9041-108ef81cbc0f |
| Android native | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/7116970a-3ae0-4c45-825c-ddf5bb5cccfb |
| Server | `WATHEFNI_PUSH_NOTIFICATIONS=on` (canary drop-in) |

## Push test

No active Expo push token for `WATHEFNI-96599338566` in DB yet (registration was previously off).

To receive the sound check:
1. Pull canary OTA (force-quit → reopen) **or** install the new native build (needed for custom `wathefni_default` sound)
2. Settings → enable **Push notifications** → allow system permission
3. Agent polls/sends: title `Wathefni` · body sound-check message · sound `wathefni_default.wav`
