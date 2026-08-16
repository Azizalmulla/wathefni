# Employee App Expo SDK 54 upgrade — 20260809T072129Z

## Verdict
**PASS** (toolchain + native IPA). Physical Home Screen icon check **PENDING** (no handset attached).

## SDK versions

| | Before | After |
|---|---|---|
| Expo | `~51.0.0` | `~54.0.0` |
| React Native | `0.74.5` | `0.81.5` |
| React | `18.2.0` | `19.1.0` |
| expo-router | `~3.5.18` | `~6.0.24` |
| App / runtimeVersion | `0.1.0` | `0.2.0` (policy: appVersion) |

## Dependency / native changes required

- Aligned Expo modules via `npx expo install` to SDK 54 peers
- Added `react-native-gesture-handler`, `react-native-reanimated@~3.19` (v3 pinned for `newArchEnabled: false`)
- Added `babel-preset-expo` (was missing; blocked Metro)
- `expo-file-system` imports → `expo-file-system/legacy`
- Push handler: `shouldShowBanner` + `shouldShowList`
- Root layout: `import 'react-native-gesture-handler'`
- `ios.icon`: `./assets/WathefniAppIcon.icon`
- EAS production `ios.image`: `macos-sequoia-15.6-xcode-26.2`
- TypeScript `~5.9.2`, `@types/react` `~19.1.10`

## Regression

- **tsc** PASS · **expo export ios** PASS
- Contract/static gates: PASS except pre-existing dirty-tree RTL `row-reverse` in Schedule (not introduced by this upgrade)
- Stop condition: no upgrade-caused meaningful regression found in automated gates

## iOS build

- Link: https://expo.dev/accounts/abdulazizalmullas-team/projects/aziz/builds/83f5955b-f9c7-45a7-a4c9-d09f696a2dcf
- IPA: https://expo.dev/artifacts/eas/n32aCuim_3lCkkA9mWT4omjJUqOH2IwhvVt02lOj2Nw.ipa
- buildNumber **22** · SDK **54.0.0** · runtime **0.2.0** · Xcode image **26.2**

## Bundling confirmation (IPA inspect)

- Icon Composer: **YES** — `WathefniAppIcon*.png` + `Assets.car` (710968 bytes)
- Push sound: **YES** — `wathefni_default.wav` byte-identical to source

## Physical icon

**PENDING** — no iPhone connected (`devicectl`: No devices found). Install IPA on canary device and compare Home Screen vs approved master.

## Rollback

1. Reinstall prior SDK 51 IPA (runtime `0.1.0`) from earlier canary builds
2. Restore `package.json` / lock from `before/` in this evidence stamp
3. Keep `version`/`runtimeVersion` at `0.1.0` for that binary line
4. Do **not** publish OTA from `0.2.0` tree to `0.1.0` natives (isolated by appVersion policy)
