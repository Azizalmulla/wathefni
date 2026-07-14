# HR-2 Native Readiness

Status: implementation and staging API proof complete; native distribution not enabled.

## Green

- Expo SDK 57.0.4 / React Native 0.86
- TypeScript passes
- Expo Doctor 20/20
- 15 frontend unit tests pass
- SecureStore access/refresh token behavior tested
- serialized refresh rotation
- capability-only workspace/navigation tests
- English/Arabic key parity and RTL preview
- reduced-motion hook and accessible labels/touch targets
- 14 preview scenarios pass in Chromium and WebKit, including refresh
- fixture preview has stable URL state, no auth redirects, no-store serving,
  service-worker removal and a top-level error boundary
- backend staging proof covers login, `/me`, leave/candidate decisions, scope,
  revocation, module removal, company disable, refresh and logout

## Intentionally not configured

- production API base URL
- production EAS credentials or project ID
- production push delivery
- TestFlight, App Store or Google Play submission

## Remaining before native distribution

- freeze the Arabic wordmark after owner review;
- provide non-production EAS project credentials;
- configure a TLS-reachable staging API base for device builds;
- run physical iOS/Android device smoke and authenticated CV document viewing;
- add production-grade app icon/splash assets without changing the in-app
  typography-only brand lockup;
- review Expo's transitive `uuid` advisory. `npm audit` reports the issue through
  Expo config/build tooling; the suggested automatic fix downgrades Expo and is
  not safe. Expo Doctor remains green.

The current EAS file contains development/design-preview profiles only and no
production profile.
