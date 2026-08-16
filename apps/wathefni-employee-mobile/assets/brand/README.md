# Wathefni brand marks — Employee App

## Canonical mark (only active badge)

`wathefni-app-icon-approved-master.png`

SHA-256: `9066753bb2c5c6940b3a9074859b8f5258c15ec9d1431ba783dee6f2ae08c4b4`

Production copies must stay **byte-identical** to this file:

- `assets/icon.png`
- `assets/adaptive-icon.png`

Flat full-bleed warm cream (`#FEF0D6`) + solid black badge only. No pre-drawn squircle frame, stroke, bevel, or metallic chrome — iOS/Android apply the system mask. Do **not** extract, crop, redraw, or re-composite the badge.

Framed predecessor (black corners): `brand/legacy/wathefni-app-icon-framed-black-corners-85884e9b.png`.

## Wiring

| Surface | Config | Asset |
|---|---|---|
| iOS Home (iOS 26 Liquid Glass) | `plugins/withLiquidGlassIcon` → `WathefniAppIcon.icon` | Icon Composer package from approved master |
| iOS fallback / Android / marketing PNG | `expo.icon` | `icon.png` (= master) |
| Android launcher | `android.adaptiveIcon.foregroundImage` | `adaptive-icon.png` (= master) |
| Android adaptive BG | `backgroundColor` | `#FEF0D6` |
| Splash | `expo.splash.image` | `splash.png` (cream canvas + **scaled** master centered; master pixels not redrawn) |
| Notification small icon | `expo-notifications.icon` | `notification-icon.png` (96px white glyph from master scale+threshold) |

See `ICON_COMPOSER.md` for Liquid Glass material settings.

## In-app UI

Typography-only `Wordmark` (“Wathefni” text) and decorative `WathefniBloom` (pastel shapes).  
Neither is a legacy PNG logo; both are intentional design-system components.

## Legacy archive

`brand/legacy/splash-legacy-serif-W-circle.png` — old circular serif-W splash (replaced).
