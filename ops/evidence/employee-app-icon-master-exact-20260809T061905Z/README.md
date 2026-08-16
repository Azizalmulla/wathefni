# Wathefni app icon — source of truth

## Approved master (do not regenerate geometry)

`wathefni-app-icon-approved-master.png`

This file is the single source of truth. Production `assets/icon.png` and
`assets/adaptive-icon.png` must be **byte-identical copies** of it.

Do **not**:
- extract / redraw the badge from code
- crop, pad, or reposition the mark
- flood-fill / “fix” the bottom anchor
- run connected-component compositors

## Wiring (`app.json`)

| Surface | Config | File |
|---|---|---|
| iOS Home / App Library / Settings / TestFlight | `expo.icon` | `assets/icon.png` (= master) |
| Android launcher (adaptive FG) | `android.adaptiveIcon.foregroundImage` | `assets/adaptive-icon.png` (= master) |
| Android adaptive BG | `android.adaptiveIcon.backgroundColor` | `#FEF0D6` |
| Android notification small icon | `expo-notifications.icon` | `assets/notification-icon.png` (96px white glyph scaled from master) |

## Prior blunder

A Python pipeline extracted the mark via connected components, resized it, and
re-composited (centered / bottom-anchored variants). That changed proportions vs
the approved master (~61% of pixels differed). Fixed by restoring the exact master.
