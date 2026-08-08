# Employee App — canary OTA publication

Published 2026-08-08T20:02:12Z by `abdulazizalmulla`.

## Identifiers

| Field | Value |
| --- | --- |
| Update group | `c997eac8-8b33-4b55-9a8e-a1860d0420fe` |
| iOS update ID | `019fe2f8-0363-7f93-8095-2abeb8647013` |
| Android update ID | `019fe2f8-0363-7c06-a114-b216af08a9cb` |
| Runtime version | `0.1.0` |
| Source commit | `1e77bf676e9a1c7c1f090833a4678ca4fd483200` (recorded by EAS as `gitCommitHash`) |
| Branch | `canary` |
| Channel | `canary` (`019fd253-0239-7802-95d7-804ab815f963`) |
| Previous group / rollback ID | `f9fc3c25-f535-40e0-b273-ef3214da93c2` |
| Rollback message | "Employee App P1 Phase 4: final functional qualification (push follow-through, FeatureUnavailable reasons, a11y/i18n)" |

Only the `canary` branch/channel was targeted. No other channel was touched, and no
native build was produced.

## Rollback

```
cd apps/wathefni-employee-mobile
npx eas-cli@latest update:republish --group f9fc3c25-f535-40e0-b273-ef3214da93c2
```

That restores the Phase 4 bundle the device was running before this publication.

## Why an OTA was sufficient (no new native build)

The installed canary iOS build is `7b3dc831-287d-4b0a-8676-eed08838ac6c`
(version 0.1.0, build 11, channel canary). Its `Expo.plist` is archived beside this
file and states:

```
EXUpdatesEnabled        = true
EXUpdatesRuntimeVersion = 0.1.0
EXUpdatesCheckOnLaunch  = ALWAYS
EXUpdatesLaunchWaitMs   = 0
expo-channel-name       = canary
```

so the installed build's runtime version is `0.1.0` and matches the published update.

`eas build:list` labels that build with commit `cf26d595`, but that label is not
usable as a dependency baseline: HEAD had not moved in a month while the working
tree kept changing, so the commit describes the repo pointer rather than the
binary's contents. The binary itself was inspected instead. Every native module the
current JS bundle requires is compiled into it:

`@react-native-async-storage/async-storage`, `@react-native-community/datetimepicker`,
`expo-constants`, `expo-device`, `expo-document-picker`, `expo-file-system`,
`expo-font`, `expo-haptics`, `expo-image-manipulator`, `expo-image-picker`,
`expo-local-authentication`, `expo-localization`, `expo-notifications`,
`expo-secure-store`, `expo-sharing`, `expo-updates`, `react-native-safe-area-context`,
`react-native-screens`, and `RCTLinking` (which backs the Phase E manager Call action).

`expo-router` is pure JS and needs no native symbol.

### One module is genuinely absent, and that is the pre-existing situation

`expo-screen-detector` (the local `modules/wathefni-screen-detector`) is **not** in
the binary — six name variants return zero symbols. Its only caller guards for
exactly this:

```
src/auth/deviceLock.ts — require() inside try/catch, returns false when the module
is missing, so timeout-based auto-lock still applies.
```

The module was already missing from the build the device is running today, so this
publication does not change behaviour. It is recorded here so it is not mistaken for
a regression during QA, and so the gap is fixed deliberately in a future native build
rather than by accident.
