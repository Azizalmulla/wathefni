# Employee App — Feedback tune (stronger haptics + restrained sound)

**Stamp:** `20260809T051843Z`  
**Verdict:** **PASS** (haptic strengthen live on canary OTA; audible layer requires new native binary)

## Scope

No visual / architecture / business-logic change. Tune native feedback so interactions are actually felt; add restrained original UI tones on high-value events only.

## What was strengthened

| Event | Before | After |
|---|---|---|
| Schedule date tap | `selectionAsync` (too subtle) | Soft impact (clearer tick; haptic-only — no sound spam on rapid taps) |
| Week swipe settle | same as day selection | Medium impact + soft `snap.wav` |
| Bottom tabs | `selectionAsync` | Soft impact via `tabFeedback` (perceptible, no sound) |
| Primary CTA press | none | Light impact on `PremiumButton` press-in (primary only; secondary quiet) |
| Success submit/upload | Success notification | Success notification + Soft follow-up + `success.wav` |
| Warning | Warning notification | Warning + Medium impact + `warning.wav` |
| Error | Error notification | Error + Heavy impact + `error.wav` |

## Where sound was added

Original short low-volume WAVs in `assets/feedback/` (sox-generated; **not** Apple assets):

| Sound | Interaction |
|---|---|
| `snap.wav` | Week strip settle |
| `success.wav` | Successful submit / upload / request |
| `warning.wav` | Consequential warning / confirm |
| `error.wav` | Blocking error |

No sound on: every button, secondary CTAs, rapid date taps, tab switches, toggles.

Audio mode: `playsInSilentModeIOS: false` (honours Silent switch), ducked on Android, volume ~0.26–0.34, fire-and-forget with throttle.

## Native note

`expo-av` is a new native dependency. Current canary OTA delivers stronger haptics immediately; **UI tones play after installing** the new iOS binary.

| | |
|---|---|
| iOS native build | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/78372a77-2dce-4c41-99c5-7525d8847f01 |
| Provisioned device | iPhone UDID `00008130-000C08563A30001C` |

Until that build is installed, sound calls no-op safely; haptics still fire.

## OTA / rollback

| | |
|---|---|
| Update group | `48be9a0a-22d5-4649-8dc7-4cedcdf1af8b` |
| Runtime | `0.1.0` |
| Rollback | `afb8371a-75ab-42af-a3d5-0f776e5488aa` |
| Gates | semantic-feedback PASS · density PASS · capability PASS · color PASS · auth-wave2 dist PASS · tsc PASS |

## Physical QA

No USB iPhone attached in this agent session. Haptic strength chosen from UIKit Soft/Medium/Heavy hierarchy (previous selection-only was the reported “barely feel” failure mode). Owner/canary device pull + post-native-install sound check recommended on: rapid Schedule taps, week swipe, tabs, primary CTA, Leave/document success, warning/error.
