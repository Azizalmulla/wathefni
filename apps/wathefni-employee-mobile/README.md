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
npm start                      # Expo dev server (use a dev client / Expo Go)
```

Set the EAS project id in `app.json` (`extra.eas.projectId`) before building or
push notifications will be disabled (the app stays fully usable via the inbox).

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
eas build --profile development --platform ios     # internal dev client
eas build --profile preview --platform all         # internal testing
eas build --profile production --platform all      # store builds
eas submit --profile production --platform all
```

Production builds strip `console.*` (see `babel.config.js`).

## Conventions

- TypeScript throughout, no `any`, no dead code, no demo/placeholder flows.
- All API calls go through `useAuth().request` (token injection + refresh) or the
  authenticated query hook in `src/lib/hooks.ts`.
- Loading / error / empty states are handled on every data screen via
  `src/components/States.tsx`.
- No secrets in the bundle: only `EXPO_PUBLIC_*` (non-secret) runtime config.
