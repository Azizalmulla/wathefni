# HR-2 Phone Review Session

Build marker: `HR2-981c7d5-20260714T053536Z`

LAN base URL:

`http://192.168.0.140:4177/design-preview`

The server is bound only to `192.168.0.140`, not `0.0.0.0`. It serves fixture
data only, sends `Cache-Control: no-store`, refuses non-RFC1918 bind addresses,
and exposes the build marker both visibly and in `X-Preview-Build`.

## Primary review URLs

- HR Home, English:
  `http://192.168.0.140:4177/design-preview?screen=home&locale=en&operator=multi-workspace&scenario=ready`
- Leave Approval, English:
  `http://192.168.0.140:4177/design-preview?screen=leave&locale=en&operator=hr-only&scenario=ready`
- AI Recruiter Candidate Review, English:
  `http://192.168.0.140:4177/design-preview?screen=candidate&locale=en&operator=recruiter-only&scenario=ready`

## English and Arabic

- HR Home, Arabic:
  `http://192.168.0.140:4177/design-preview?screen=home&locale=ar&operator=multi-workspace&scenario=ready`
- Leave Approval, Arabic:
  `http://192.168.0.140:4177/design-preview?screen=leave&locale=ar&operator=restricted-manager&scenario=ready`
- Candidate Review, Arabic:
  `http://192.168.0.140:4177/design-preview?screen=candidate&locale=ar&operator=recruiter-only&scenario=ready`

## Operator and scenario matrix

- HR-only, empty:
  `http://192.168.0.140:4177/design-preview?screen=home&locale=en&operator=hr-only&scenario=empty`
- Restricted manager, revoked permission:
  `http://192.168.0.140:4177/design-preview?screen=home&locale=en&operator=restricted-manager&scenario=revoked`
- HR-only, disabled company:
  `http://192.168.0.140:4177/design-preview?screen=home&locale=en&operator=hr-only&scenario=company-disabled`
- HR-only, loading:
  `http://192.168.0.140:4177/design-preview?screen=leave&locale=en&operator=hr-only&scenario=loading`
- HR-only, stale decision:
  `http://192.168.0.140:4177/design-preview?screen=leave&locale=en&operator=hr-only&scenario=stale`
- HR-only, successful decision:
  `http://192.168.0.140:4177/design-preview?screen=leave&locale=en&operator=hr-only&scenario=success`
- Multi-workspace, error:
  `http://192.168.0.140:4177/design-preview?screen=candidate&locale=en&operator=multi-workspace&scenario=error`
- Multi-workspace, revoked permission:
  `http://192.168.0.140:4177/design-preview?screen=candidate&locale=en&operator=multi-workspace&scenario=revoked`

## Verification

- listener: `192.168.0.140:4177` only;
- preview scenarios: `14 × Chromium + WebKit`, all passed;
- URL state preserved after reload in both engines;
- stale service-worker registration count: `0`;
- screenshots regenerated for all three screens in English and Arabic;
- TypeScript: passed;
- frontend tests: `15/15`;
- Expo Doctor: `20/20`.

Final physical iPhone Safari acceptance requires opening the URLs on the same
Wi-Fi and reloading at least one English and one Arabic URL. Automated WebKit
proof is complete, but it is not a substitute for the reviewer’s physical
device confirmation.
