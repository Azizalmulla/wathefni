# Wathefni HR Mobile

> **SHIP RETIRED as a public app.** See `SHIP_RETIRED.md`.
> HR now ships inside the public Wathefni binary (`apps/wathefni-employee-mobile`)
> under `/hr/*` with a separate operator principal.

Separate Expo SDK 57 **source package** for authorized company operators (legacy).
It is not an Employee App workspace and cannot call employee or legacy recruiter APIs.

## Boundaries

Allowed:

- `/dashboard/mobile/auth/*`
- `/dashboard/mobile/me`
- approved `/dashboard/mobile/*` data adapters

Rejected by the API client:

- employee `/app/*` and `/app/auth/*`
- Setup Console routes
- legacy `ai-recruiter/` routes
- non-mobile dashboard routes

Tokens are stored only with `expo-secure-store` using
`WHEN_UNLOCKED_THIS_DEVICE_ONLY`. Refresh rotation is serialized so concurrent
requests cannot replay an old refresh token.

## Local checks

```sh
npm run typecheck
npm test
npm run expo:doctor
npm run preview:export
npm run preview:serve
npm run preview:verify
```

## HR-3 route inventory

All production data calls remain under `/dashboard/mobile/*`. Workspace links are
derived only from `/dashboard/mobile/me` workspaces, features and actions; role
names are display metadata and never grant a route.

- `/` — capability-shaped priorities and workspace navigation
- `/tasks` — authorized HR task queue
- `/leave/[id]` — retained leave review and confirmed decision flow
- `/onboarding` and `/onboarding/[employeeKey]` — onboarding review
- `/documents` and `/documents/[employeeKey]/[documentType]` — document review
- `/attendance` and `/attendance/[attendanceId]` — attendance review and confirmed resolution
- `/shifts` and `/shift-swaps/[swapId]` — today’s shifts and swap decisions
- `/employees` and `/employees/[employeeKey]` — grant-only directory and profile
- `/delivery-alerts` — communication delivery operations
- `/candidates` and `/candidates/[appKey]` — ranked list, evidence-separated
  review, authenticated CV access, and confirmed human decisions
- `/interviews` and `/interviews/[interviewId]` — status, delivery and notes
- `/settings` — company, operator, scope, locale, authority refresh and sessions

Settings intentionally has no Setup Console, ownership or company-control
surface.

Capability-to-route details, endpoint envelope assumptions and state handling
are recorded in `docs/HR3_FRONTEND.md`.

## Fixture-only design preview

Build:

```sh
npm run preview:export
npm run preview:serve
```

Open:

`http://127.0.0.1:4177/design-preview?view=home&locale=en&operator=multi-workspace&scenario=ready&controls=0`

URL state:

- `view=sign-in|home|tasks|onboarding|documents|attendance|shifts|shift-swap|employees|employee-profile|delivery-alerts|candidates|candidate|interviews|interview|settings|leave`
- `locale=en|ar`
- `operator=hr-only|recruiter-only|restricted-manager|multi-workspace`
- `scenario=ready|loading|empty|error|offline|permission|revoked|company-disabled|company-archived|session-expired|stale|success`
- `controls=0` hides the control chrome for clean phone review links
- `capture=1` hides preview controls for screenshots
- Prefer `view=` over legacy `screen=` (Expo Router reserves `screen`)

The preview:

- uses the production shared screen components and capability-shaped fixtures;
- has no authentication redirect;
- has a top-level error boundary;
- unregisters old service workers;
- is served with `no-store` headers;
- performs no network request or mutation;
- has Chromium and WebKit reload verification.

## Current review checkpoint

The provisional Arabic wordmark is `وظفني للموارد البشرية`. It remains subject
to owner visual review before freezing.

The DB-backed staging contract is green. Native authenticated PDF handoff still
requires signed development-build testing. Production, EAS credentials, push
delivery, TestFlight and store submission remain intentionally untouched.
