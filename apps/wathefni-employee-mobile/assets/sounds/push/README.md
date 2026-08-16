# Wathefni push notification sounds

## Chosen default (normal)

Source audition pick: `source/universfield-new-notification-040-493469.mp3`  
Native default (decode-only, no remaster): `wathefni_default.wav` (+ `wathefni_default.caf` reference)

Prior audition (kept for history): `source/universfield-new-notification-051-494246.mp3`

Urgent/time-sensitive: not selected yet — leave separate.

## Platform formats

| Platform | Requirement | Our asset |
|---|---|---|
| iOS (APNs custom) | Linear PCM / MA4 in `.wav`, `.aiff`, or `.caf`. **Not MP3/AAC in the bundle for custom sounds.** ≤ 30s | `wathefni_default.wav` (PCM s16le, 44.1 kHz, stereo, ~1.07s) |
| Android (FCM / channel) | File in `res/raw` (`.wav` / `.mp3` / `.ogg`). Channel sound is authoritative on Android 8+ | Same WAV copied by Expo plugin; channel id `wathefni_default_v2` |

Volume and duration were left unchanged from the source MP3 (lossless PCM decode only).

Android channel id is bumped when the WAV content changes (`wathefni_default` → `wathefni_default_v2` for the 040 tone).
