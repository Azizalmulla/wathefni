# Wathefni Employee App (V1)

A calm, focused employee self-service app for iOS and Android. It is a thin client
over the shared Wathefni backend (`wathefni-orchestrator`) — same backend, same
database, same tenancy as the HR dashboard — talking only to the employee-scoped
`/app/*` API surface.

It is NOT a second HR dashboard. Scope is deliberately small: receive push
notifications, see an inbox, complete simple self-service actions.

## Stack

- Expo (managed) + React Native + TypeScript
- expo-router (file-based navigation)
- @tanstack/react-query (server state, loading/error states)
- expo-secure-store (session tokens in the OS keychain/keystore — never AsyncStorage)
- expo-notifications (push), expo-document-picker / expo-image-picker (uploads)
- i18n-js + expo-localization (English + Arabic, RTL-aware)

## Getting started

```bash
cd apps/wathefni-employee-mobile
npm install
cp .env.example .env          # set EXPO_PUBLIC_API_BASE_URL (staging by default)
npx expo install              # align native module versions with the installed Expo SDK
npm run start:dev-client       # after installing the EAS development build
```

Follow `docs/NATIVE_DEVELOPMENT_BUILD.md` before building. The EAS project ID is
required for a development client and push token registration.

## V1 screens

Activation/login, Home, Notifications inbox, Shifts (today + upcoming), Leave
(balance, request, status, cancel), Onboarding (checklist + upload), Documents,
Attendance, Profile, Settings (language, push, privacy, account-deletion request).

## Authentication

HR-provisioned activation: HR issues a single-use code from the dashboard
("Invite to App"); the employee enters phone + code to activate. Sessions are
opaque bearer tokens (access + refresh) held in secure storage; the client
refreshes transparently on a 401. There is no open self-registration. Offboarding
an employee instantly revokes their sessions and push tokens server-side.

## Data boundaries

The app never sends an `employee_key` or `company_code` — identity is always
derived server-side from the verified session. Every screen shows only the
signed-in employee's own data.

## Builds (EAS)

```bash
npx eas-cli build --profile development --platform ios
```

Production builds strip `console.*` (see `babel.config.js`).
Production push registration remains disabled until delivery is explicitly approved.

## Production references

- Permanent design reference: `docs/DESIGN_SYSTEM.md`
- Native build onboarding: `docs/NATIVE_DEVELOPMENT_BUILD.md`
- Performance: `docs/PHASE_9B_PERFORMANCE.md`
- Accessibility: `docs/PHASE_9B_ACCESSIBILITY.md`
- Engineering audit: `docs/PHASE_9B_ENGINEERING_AUDIT.md`
- Readiness decision: `docs/PHASE_9B_READINESS.md`

## Conventions

- TypeScript throughout, no `any`, no dead code, no demo/placeholder flows.
- All API calls go through `useAuth().request` (token injection + refresh) or the
  authenticated query hook in `src/lib/hooks.ts`.
- Loading / error / empty states are handled on every data screen via
  `src/components/States.tsx`.
- No secrets in the bundle: only `EXPO_PUBLIC_*` (non-secret) runtime config.
