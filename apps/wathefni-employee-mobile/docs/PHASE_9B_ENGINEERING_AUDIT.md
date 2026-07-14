# Phase 9B Engineering Audit

## Resolved

- Removed the shipping `/design-preview` route, synthetic fixtures, browser-only error boundary, static preview server, capture scripts, WebKit verifier, preview flags, cache purge, and Playwright dependency.
- Replaced the preview-only skeleton name with the permanent `ContentSkeleton`.
- Added a production-safe root error boundary that does not expose stack traces or bearer data.
- Added request cancellation through React Query abort signals.
- Added cleanup for native upload/download tasks on cancellation and route unmount.
- Removed notification permission prompting from Home. Permission is now user-initiated from Settings after a rationale.
- Added silent push re-registration only when permission already exists, token-change handling, notification response routing, listener cleanup, and best-effort logout unregistration.
- Push registration is enabled only in development/internal profiles; production is explicitly off.
- Added native light haptics to deliberate primary actions.
- Fixed headerless Home safe-area handling and 44-point control minimums found in the audit.
- Limited the native icon bundle to Ionicons.

## Architecture retained

- `AuthProvider` remains the single authority for access/refresh tokens, 401 rotation, access states, downloads, and uploads.
- The app never sends employee or company identity; the backend derives both from the session.
- Feature visibility and action availability remain driven by `/app/me`.
- Presentational feature views remain separated from route/query/mutation code.
- React Query owns server state; local state is limited to forms and active native transfers.

## Open findings

### Blocking

1. The app is on Expo SDK 51 while the current npm release is Expo 57. The audit reports 37 transitive advisories (22 high, 14 moderate, 1 low), largely in SDK/CLI build tooling. Fixes require a major Expo/React Native migration, not `npm audit fix --force`.
2. `extra.eas.projectId` is still a placeholder and EAS authentication is unavailable on this machine.
3. No approved App Store icon or splash asset exists.
4. There is no crash/diagnostic service configured for release builds.
5. The privacy policy is still a legal draft and must be approved and published at the configured public URL.
6. Android push testing will require Firebase/FCM V1 credentials and an approved monochrome notification icon before production delivery can be enabled.

### Requires backend or product contract

- Inbox, Leave, and Documents responses have no pagination contract. Do not let these arrays become unbounded without virtualized/paginated APIs.
- Push settings expose registration state derived from OS permission; the backend does not currently return a per-device preference/status resource.
- Secure external-provider document responses may return an HTTPS access URL. The client validates HTTPS and never places its bearer token in a URL, but expiry and provider-domain policy remain backend responsibilities.

### Physical-device verification

- Native startup, memory, camera memory pressure, upload interruption, document preview behavior, VoiceOver, and Dynamic Type require a signed development build and an iPhone.
- Navigation/access-state races should be exercised while the company or employee is disabled between foreground transitions.

## Dependency decision

Do not suppress or force-fix the audit. Schedule an SDK 51 → 57 migration as a controlled native compatibility slice, rerun Expo Doctor after each supported upgrade step, regenerate native projects, and repeat the complete English/Arabic and transfer test matrix.
