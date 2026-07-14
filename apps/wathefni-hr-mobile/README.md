# Wathefni HR Mobile

Separate Expo SDK 57 application for authorized company operators. It is not an
Employee App workspace and cannot call employee or legacy recruiter APIs.

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

## Fixture-only design preview

Build:

```sh
npm run preview:export
npm run preview:serve
```

Open:

`http://127.0.0.1:4177/design-preview?view=home&locale=en&operator=multi-workspace&scenario=ready`

URL state:

- `view=home|leave|candidate`
- `locale=en|ar`
- `operator=hr-only|recruiter-only|restricted-manager|multi-workspace`
- `scenario=ready|loading|empty|error|revoked|company-disabled|stale|success`
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

Staging API connection, production EAS credentials, push delivery and store
submission are intentionally not configured in this slice.
