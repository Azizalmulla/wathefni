# Wathefni brand marks — Employee App

## Canonical mark (only active badge)

`wathefni-app-icon-approved-master.png`

SHA-256: `85884e9b75fb3478ac788e536c88d02a8f06d83715deb4ab904028922a24c231`

Production copies must stay **byte-identical** to this file:

- `assets/icon.png`
- `assets/adaptive-icon.png`

Do **not** extract, crop, redraw, or re-composite the badge.

## Wiring

| Surface | Config | Asset |
|---|---|---|
| iOS Home / App Library / Settings / TestFlight | `expo.icon` | `icon.png` (= master) |
| Android launcher | `android.adaptiveIcon.foregroundImage` | `adaptive-icon.png` (= master) |
| Android adaptive BG | `backgroundColor` | `#FEF0D6` |
| Splash | `expo.splash.image` | `splash.png` (cream canvas + **scaled** master centered; master pixels not redrawn) |
| Notification small icon | `expo-notifications.icon` | `notification-icon.png` (96px white glyph from master scale+threshold) |

## In-app UI

Typography-only `Wordmark` (“Wathefni” text) and decorative `WathefniBloom` (pastel shapes).  
Neither is a legacy PNG logo; both are intentional design-system components.

## Legacy archive

`brand/legacy/splash-legacy-serif-W-circle.png` — old circular serif-W splash (replaced).
