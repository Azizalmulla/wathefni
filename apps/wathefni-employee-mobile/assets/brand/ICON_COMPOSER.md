# Wathefni iOS Icon Composer package

Production package: `assets/WathefniAppIcon.icon`

## Source of truth

Badge geometry/placement comes from `assets/brand/wathefni-app-icon-approved-master.png` (flat cream `#FEF0D6` + solid black badge). The badge is extracted as `Assets/badge.png` (black + alpha) without changing proportions or position.

## Liquid Glass tuning (Default / Light)

Configured to counteract iOS 26 Home Screen frost/greying on the black mark:

| Property | Value | Why |
| --- | --- | --- |
| Document fill | solid `#FEF0D6` (`fill-specializations` default + dark) | Warm cream plate; Default appearance = Light |
| Layer `glass` | `false` | Avoid frosting the badge |
| Group `specular` | `false` | Kill specular greying on black |
| Group `translucency` | disabled / `0` | Kill see-through haze |
| Group `shadow` | `none` / `0` | No added shadow |
| `blur-material` | `0` | No thick glass plate behind mark |
| `refractivity` | disabled | No refraction softening |

No custom chrome, bevel, border, or shadow is baked into the artwork.

## Wiring (Expo SDK 54+)

Native path: `app.json` → `ios.icon: "./assets/WathefniAppIcon.icon"` (Expo SDK 54+).

Requires EAS/Xcode **26+** (`eas.json` production `ios.image`). Legacy PNG remains at `expo.icon` for Android/marketing fallback.

Optional legacy plugin `plugins/withLiquidGlassIcon.js` is retained but unused when `ios.icon` is set.

## Validate locally

```bash
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
ICTOOL="/Applications/Xcode.app/Contents/Applications/Icon Composer.app/Contents/Executables/ictool"
"$ICTOOL" assets/WathefniAppIcon.icon --export-preview iOS Default 1024 1024 1 /tmp/wathefni-default.png
```
