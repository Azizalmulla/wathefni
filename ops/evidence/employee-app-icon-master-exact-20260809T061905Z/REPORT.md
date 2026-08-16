# App icon pipeline audit — exact approved master

**Stamp:** `20260809T061905Z`  
**Verdict:** **PASS** (exact master restored; native rebuild required)

## Exact source now in use

| Role | Path | SHA-256 (prefix) |
|---|---|---|
| Approved master (SoT) | `apps/wathefni-employee-mobile/assets/brand/wathefni-app-icon-approved-master.png` | `85884e9b75fb3478…` |
| iOS icon | `apps/wathefni-employee-mobile/assets/icon.png` | **byte-identical** to master |
| Android adaptive FG | `apps/wathefni-employee-mobile/assets/adaptive-icon.png` | **byte-identical** to master |

Owner upload archived as that master (from `9543F98E-…-e39870c3-….png`).

## `app.json` wiring (all resolve to that source)

| Surface | Key | File |
|---|---|---|
| iOS Home / App Library / Settings / TestFlight | `expo.icon` | `./assets/icon.png` |
| Android launcher | `android.adaptiveIcon.foregroundImage` | `./assets/adaptive-icon.png` |
| Android adaptive BG | `android.adaptiveIcon.backgroundColor` | `#FEF0D6` |
| Android notification glyph | `expo-notifications.plugin.icon` | `./assets/notification-icon.png` (96px scale+threshold of same master only) |

No other icon paths referenced. No generator scripts in `scripts/` / `package.json`.

## What caused the distorted native icon

Not Expo cache inventing art — **our asset pipeline rewrote the badge**:

1. Connected-component extraction of the black mark from an earlier PNG  
2. Resize to ~62–68% / side-pad fractions  
3. Re-composite (centered, then “bottom-anchored”) onto a new cream canvas  

Measured vs approved master: **~61% of pixels differed** (mean abs channel diff ~311). Internal proportions and bottom flush from the master were lost.

A later “flood-fill exterior to cream” attempt also **ate the logo**, because the mark is bottom-flush into the pre-rounded mask edge and flood-fill walked into the ink.

## Fix

- Stop all redraw/crop/reposition  
- Ship **byte-identical** copies of the approved master as `icon.png` + `adaptive-icon.png`  
- Home-screen icon requires **new native build** (not OTA)


## Native builds (exact master baked)

| Platform | URL |
|---|---|
| iOS | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/74d71dbb-3a53-4260-ac38-b01178960063 |
| Android | https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/c3b7c0da-14ea-4501-8078-02be7a492e45 |
