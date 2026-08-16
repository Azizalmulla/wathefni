# iOS 26 Icon Composer tune — FAIL (blocked on toolchain)

## Current icon path / type (installed build)

| Field | Value |
| --- | --- |
| Build | `78bb78be-dde2-4d8c-b7db-449e6d97a59f` (buildNumber 19) |
| EAS image | `macos-sonoma-14.5-xcode-15.4` |
| Config | top-level `expo.icon` → `./assets/icon.png` |
| Native type | Legacy PNG → `Images.xcassets/AppIcon.appiconset` |
| Explicit Icon Composer `.icon` | **No** |

## Was iOS auto-adapting the legacy asset?

**Yes.** With only a flat PNG AppIcon and no Icon Composer package, iOS 26 applies automatic Liquid Glass / specular treatment. That matches the physical Home Screen look (softer/greyer badge, hazy specular).

## Icon Composer package created

Path: `apps/wathefni-employee-mobile/assets/WathefniAppIcon.icon`

Layers:
- Document fill: solid `#FEF0D6` (Default + Dark specializations)
- Foreground group / Badge layer: black+alpha badge extracted from approved master (geometry/placement unchanged)

Material settings (Default/Light):
- `glass: false`
- `specular: false`
- `translucency: disabled / 0`
- `shadow: none`
- `blur-material: 0`
- `refractivity: disabled`

`ictool` Default preview vs master (badge mean luminance): master `0.074` · Composer `0.075` (no frosting regression in Composer preview).

Plugin: `plugins/withLiquidGlassIcon.js` (gated by `WATHEFNI_IOS_ICON_COMPOSER=1`).

## Native ship attempt

| Field | Value |
| --- | --- |
| Build | `4146bebf-3af3-4727-bf88-86e37c77fd47` |
| Image | `macos-sequoia-15.6-xcode-26.2` (required for `.icon`) |
| Result | **ERRORED** `XCODE_BUILD_ERROR` — `switch must be exhaustive` |
| Cause | Expo SDK **51** is not buildable on Xcode 26; not an icon-geometry failure |

## Physical before / after

| | Result |
| --- | --- |
| Before (installed) | Legacy PNG + iOS 26 auto Liquid Glass → soft/grey badge (owner-reported; consistent with path above) |
| After | **Not available** — no installable IPA (Xcode 26 build failed). Cannot compare physical Home Screen yet. |

## Verdict

**FAIL** for on-device Icon Composer delivery.

Unblocked next step: upgrade Employee App to Expo SDK 54+ (native `ios.icon` + Xcode 26), then enable `WATHEFNI_IOS_ICON_COMPOSER=1` (or switch to stock `ios.icon`) and re-qualify on the physical iPhone.
