# Native iPhone Development Build

This project includes `expo-dev-client` and an internal EAS `development` profile. It targets staging and enables push registration only in development/internal builds.

## One-time owner setup

1. Install Xcode locally if simulator or local archive work is required.
2. Sign in with the Wathefni Expo account:

   ```bash
   npx eas-cli login
   npx eas-cli whoami
   ```

3. Link or create the correct EAS project:

   ```bash
   npx eas-cli init
   ```

   Confirm that `app.json` receives a real `expo.extra.eas.projectId`. Do not build while it contains `REPLACE_WITH_EAS_PROJECT_ID`.

4. Confirm the Apple team owns `ai.wathefni.employee`. Register the physical iPhone for internal distribution:

   ```bash
   npx eas-cli device:create
   ```

5. Provide approved app icon and splash assets before distributing outside engineering.

## Build and install

```bash
cd apps/wathefni-employee-mobile
npm ci
npm run typecheck
npm run native:doctor
npx eas-cli build --profile development --platform ios
```

Open the EAS installation URL on the registered iPhone and install the development client. Trust/enable Developer Mode if iOS requests it.

Start Metro on the same reachable network:

```bash
npm run start:dev-client
```

Open Wathefni, select the local development server, and sign in only against the staging backend.

## Stable tester onboarding

- Record the EAS build ID, git commit, device model, iOS version, locale, and staging test employee.
- Test a clean install first, then upgrade-in-place.
- Exercise Activation, foreground/background, EN↔AR, every enabled capability, camera/library/files upload, cancellation/retry, document preview/share/cancel, push opt-in/out, logout, and every backend access state.
- Repeat with Reduced Motion, VoiceOver, largest Dynamic Type, offline/reconnect, denied permissions, and revoked permissions.
- Remove the development profile/app from devices when testing ends.

## Important boundaries

- The production EAS profile sets `EXPO_PUBLIC_PUSH_REGISTRATION_ENABLED=0`.
- This procedure does not create a TestFlight build, submit to Apple, touch production, or enable production push delivery.
- Development-client metrics are not release-build startup or memory metrics.

## Current setup blockers

- EAS CLI reports “Not logged in”.
- `extra.eas.projectId` is a placeholder.
- `simctl` is unavailable because the active developer tools do not include a full Xcode installation.
