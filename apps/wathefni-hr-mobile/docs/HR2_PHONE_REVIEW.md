# HR-2 Phone Review Session

Build marker: `HR2-cec34b9-20260714T085130Z`

LAN base URL:

`http://192.168.0.140:4177/design-preview`

The server is bound only to `192.168.0.140`, not `0.0.0.0`. It serves fixture
data only, sends `Cache-Control: no-store`, refuses non-RFC1918 bind addresses,
and exposes the build marker both visibly and in `X-Preview-Build`.

On iPhone Safari, controls start collapsed. A floating **Controls** button opens
a bottom sheet; choosing a screen, locale, operator, or scenario closes it.
Desktop keeps the expanded control panel. Use `controls=0` for clean review
links with the mockup as the only focus (no control chrome).

Preview selection uses `view=` (not `screen=` — Expo Router reserves `screen`).
Legacy `?screen=` deep links are still read from the raw query string on load.

## Direct review URLs (controls hidden)

- HR Home:
  `http://192.168.0.140:4177/design-preview?view=home&locale=en&operator=multi-workspace&scenario=ready&controls=0`
- Leave Approval:
  `http://192.168.0.140:4177/design-preview?view=leave&locale=en&operator=hr-only&scenario=ready&controls=0`
- Candidate Review:
  `http://192.168.0.140:4177/design-preview?view=candidate&locale=en&operator=recruiter-only&scenario=ready&controls=0`
- Arabic HR Home:
  `http://192.168.0.140:4177/design-preview?view=home&locale=ar&operator=multi-workspace&scenario=ready&controls=0`

## Primary review URLs (with controls available)

- HR Home, English:
  `http://192.168.0.140:4177/design-preview?view=home&locale=en&operator=multi-workspace&scenario=ready`
- Leave Approval, English:
  `http://192.168.0.140:4177/design-preview?view=leave&locale=en&operator=hr-only&scenario=ready`
- AI Recruiter Candidate Review, English:
  `http://192.168.0.140:4177/design-preview?view=candidate&locale=en&operator=recruiter-only&scenario=ready`

## English and Arabic

- HR Home, Arabic:
  `http://192.168.0.140:4177/design-preview?view=home&locale=ar&operator=multi-workspace&scenario=ready`
- Leave Approval, Arabic:
  `http://192.168.0.140:4177/design-preview?view=leave&locale=ar&operator=restricted-manager&scenario=ready`
- Candidate Review, Arabic:
  `http://192.168.0.140:4177/design-preview?view=candidate&locale=ar&operator=recruiter-only&scenario=ready`

## Operator and scenario matrix

- HR-only, empty:
  `http://192.168.0.140:4177/design-preview?view=home&locale=en&operator=hr-only&scenario=empty&controls=0`
- Restricted manager, revoked permission:
  `http://192.168.0.140:4177/design-preview?view=home&locale=en&operator=restricted-manager&scenario=revoked&controls=0`
- HR-only, disabled company:
  `http://192.168.0.140:4177/design-preview?view=home&locale=en&operator=hr-only&scenario=company-disabled&controls=0`
- HR-only, loading:
  `http://192.168.0.140:4177/design-preview?view=leave&locale=en&operator=hr-only&scenario=loading&controls=0`
- HR-only, stale decision:
  `http://192.168.0.140:4177/design-preview?view=leave&locale=en&operator=hr-only&scenario=stale&controls=0`
- HR-only, successful decision:
  `http://192.168.0.140:4177/design-preview?view=leave&locale=en&operator=hr-only&scenario=success&controls=0`
- Multi-workspace, error:
  `http://192.168.0.140:4177/design-preview?view=candidate&locale=en&operator=multi-workspace&scenario=error&controls=0`
- Multi-workspace, revoked permission:
  `http://192.168.0.140:4177/design-preview?view=candidate&locale=en&operator=multi-workspace&scenario=revoked&controls=0`

## Verification

- listener: `192.168.0.140:4177` only;
- preview scenarios include WebKit/Chromium checks for `controls=0`, page scrollability, and mobile control sheet open/close;
- URL state preserved after reload;
- stale service-worker registration count: `0`;
- screenshots regenerated with controls hidden;
- TypeScript / frontend tests / Expo Doctor as recorded after the latest export.

Physical iPhone Safari acceptance: open a `controls=0` URL on the same Wi-Fi,
scroll to the bottom of Home / Leave / Candidate, open/close Controls when not
using `controls=0`, and confirm safe-area padding above the Safari chrome.
