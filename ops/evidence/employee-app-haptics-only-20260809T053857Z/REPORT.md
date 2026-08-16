# Employee App — In-app haptics only (remove UI tones)

**Stamp:** `20260809T053857Z`  
**Verdict:** **PASS**

## Scope

Remove custom in-app UI sounds. Keep strengthened haptics. Push `wathefni_default` unchanged.

## Removed

- In-app playback of `snap` / `success` / `warning` / `error` from `src/native/haptics.ts`
- Assets: `assets/feedback/{snap,success,warning,error}.wav`
- Dependency: `expo-av` (not required for push; push uses `expo-notifications` bundled sound)

## Kept (haptics)

| Event | Haptic |
|---|---|
| Schedule date | Soft impact |
| Week swipe settle | Medium impact |
| Bottom tabs | Soft impact (`tabFeedback`) |
| Primary CTA press | Light impact |
| Success / warning / error | Notification + Soft / Medium / Heavy follow-up |

## Push (untouched)

| | |
|---|---|
| Asset | `assets/sounds/push/wathefni_default.wav` (+ source Universfield MP3) |
| Plugin | `expo-notifications.sounds` + `defaultChannel: wathefni_default` |
| Client | Android channel `wathefni_default` |
| Server | Expo payload `sound: wathefni_default.wav` + `channelId: wathefni_default` |

## OTA / rollback

| | |
|---|---|
| Update group | `517be51a-902e-482a-8a78-869a16f0b8d4` |
| Runtime | `0.1.0` |
| Rollback | `bd9e4015-e503-4f6d-9026-f1cd2a83a6d4` |
| Gates | semantic-feedback PASS · push-sound PASS · density PASS · capability PASS · auth-wave2 dist PASS · tsc PASS |
