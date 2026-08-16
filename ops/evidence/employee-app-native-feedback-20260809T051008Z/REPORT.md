# Employee App — Native micro-feedback

**Stamp:** `20260809T051008Z`  
**Verdict:** **PASS** (canary OTA · static gates · no physical iPhone attached this session)

## Scope

Native micro-feedback only. No screen redesign. No product architecture change. Central semantic layer; screens call events, not raw `expo-haptics`.

## Semantic feedback map

| Event | Use | iOS (`expo-haptics`) | Android |
|---|---|---|---|
| `selection` | Schedule day tap · week swipe settle · tab press · toggles · compact selectors · locale | `selectionAsync` | Platform selection / light vibration mapping |
| `lightImpact` | Rare deliberate impact only (alias `actionHaptic`; **not** on every button) | `impactAsync(Light)` | Light impact mapping |
| `success` | Primary successful Leave / document / bank / onboarding / payslip / PIN / push-on / deletion-requested | `notificationAsync(Success)` | Success notification mapping |
| `warning` | Consequential confirms (cancel leave, bank withdraw, sign-out, delete account) · push denied · onboarding validation | `notificationAsync(Warning)` | Warning notification mapping |
| `error` | Failed transfers / blocking errors shown to the employee | `notificationAsync(Error)` | Error notification mapping |

Call sites use `selectionFeedback` / `successFeedback` / `warningFeedback` / `errorFeedback` (or `feedback.*`).

## Performance safeguards

- Fire-and-forget (`void` + catch) — never awaited; never blocks navigation/UI
- Per-kind throttle: selection 90ms · lightImpact 120ms · success/warning/error 220ms
- No queue / no overlapping stack on rapid taps
- Schedule: haptic only on `tap` and swipe **settle** (`onMomentumScrollEnd`) — **not** while dragging
- `PremiumButton` has **no** blanket haptic
- Rapid Schedule date taps remain `startTransition`-isolated; throttle preserves week-strip perf fix
- Web no-op; native failures swallowed

## OTA / rollback

| | |
|---|---|
| Update group | `afb8371a-75ab-42af-a3d5-0f776e5488aa` |
| Runtime | `0.1.0` (JS OTA compatible) |
| Rollback | `96703a6f-3f52-4c1f-8e64-8aa72000ad7e` |
| Gates | semantic-feedback PASS · density PASS · capability PASS · color PASS · auth-wave2 dist PASS · tsc PASS |

## Physical QA

No USB iPhone attached in this environment. Highest-value interactions are live on canary for Aziz/Talal after pull: rapid Schedule date taps, week swipe settle, tab switch, Leave/document/bank/onboarding success, error/warning confirms.
