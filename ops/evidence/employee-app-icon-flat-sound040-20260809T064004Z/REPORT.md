# Flat icon + Universfield 040 push sound — 20260809T064004Z

## Icon
- Full-bleed flat cream `#FEF0D6` + solid black badge
- No pre-drawn squircle frame / dark outline / chrome
- Badge geometry/placement preserved from framed master `85884e9b…` (interior badge ink positions unchanged; exterior black→cream; cream field forced solid)
- SHA-256 master/icon/adaptive: `9066753bb2c5c6940b3a9074859b8f5258c15ec9d1431ba783dee6f2ae08c4b4`
- Legacy framed archive: `assets/brand/legacy/wathefni-app-icon-framed-black-corners-85884e9b.png`

## Push sound
- Source: `universfield-new-notification-040-493469.mp3` (~1.07s)
- Bundled: `wathefni_default.wav` (pcm_s16le 44.1kHz stereo, decode-only)
- Android channel bumped: `wathefni_default` → `wathefni_default_v2` (channel sound immutable)
- Orchestrator `channelId`: `wathefni_default_v2`

## Gates
- verify-push-sound PASS
- verify-semantic-feedback PASS

## Ship
- Android EAS: `82f00604-687b-4d00-a5bc-1ca8b92de66d` (versionCode 11, in progress)
- iOS EAS: blocked — Free plan iOS quota exhausted until 2026-09-01
- Orchestrator `channelId` bump must be deployed for Android to play the new channel sound
- OTA alone insufficient for icon + bundled sound
