# HR-3 Preview Matrix

The fixture-only design preview keeps a single page-level scroller. Embedded
production `Screen` components continue to suppress their nested `ScrollView`
through `PreviewEmbedProvider`.

Primary view inventory:

- Sign-in and the capability/workspace home shell
- Tasks, onboarding, documents, attendance, shifts and shift-swap detail
- Employees, employee quick profile and delivery alerts
- Ranked candidates, candidate review, interviews and interview detail
- Settings and retained leave review

Operator inventory:

- HR-only
- Recruiter-only
- Restricted manager
- Multi-workspace

State inventory:

- Ready, loading, empty, generic error and offline
- Permission/scope denial and revoked/disabled access
- Company disabled, company archived and session expired
- Stale and successful mutation outcomes

Clean links use `view=` because Expo Router reserves `screen`. Examples:

- `/design-preview?view=tasks&locale=en&operator=hr-only&scenario=ready&controls=0`
- `/design-preview?view=employees&locale=ar&operator=multi-workspace&scenario=ready&controls=0`
- `/design-preview?view=candidates&locale=en&operator=recruiter-only&scenario=ready&controls=0`
- `/design-preview?view=interviews&locale=ar&operator=multi-workspace&scenario=offline&controls=0`

Mobile controls start collapsed. `controls=0` removes controls entirely.
The HR-3 build marker exists only in the design-preview route, uses reduced
non-overlapping chrome, and fades after a short delay outside capture mode.

`scripts/verify-preview.mjs` verifies URL state, no-store headers, the build
marker, reload behavior, one effective scroller and absence of embedded scroll
traps in Chromium and WebKit. It also captures EN/AR primary-view screenshots
and writes `docs/screenshots/HR3_SCREENSHOT_MAP.json`.

The refreshed LAN preview is exported with an HR-3 build marker. The automated
gate covers 32 scenarios in Chromium and WebKit and captures every listed view
in English and Arabic.
