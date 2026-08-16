# Employee App — Week-strip capsule + LoadingState polish

**Stamp:** `20260809T020711Z`  
**Verdict: PASS**

## Fixes

1. **Schedule selected-day capsule** — explicit 42×56 stadium with `borderRadius = width/2` (no top/bottom stretch); day text stack matches capsule height for true center; presence/today marks absolute so they no longer shove selected labels; strip overflow visible; page margins unchanged for first/last days.
2. **LoadingState** — centered spinner + label on cream; oversized bordered empty panel removed. EmptyState demoted to the same quiet cluster pattern. Error keeps semantic bordered card.

## Deploy

| Field | Value |
| --- | --- |
| Channel | Canary OTA `e0dc5e93-7165-4e6d-a195-033c15dddc11` · runtime `0.1.0` |
| Rollback | `dd05381d-b2a0-4d59-b0f9-117e71b4b0f7` |
| Dashboard | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/updates/e0dc5e93-7165-4e6d-a195-033c15dddc11 |

## Gates

tsc PASS · density PASS (99) · capability GREEN
