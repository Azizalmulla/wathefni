# HR Mobile — Navigation ergonomics debt

Stamp: after B1–B4 remediation (safe-back contract).

## Fixed (do not reopen without product change)

| Item | Resolution |
| --- | --- |
| B1 Legacy details missing Back | `WorkspaceHeader`/`Leave`/`Candidate`/`OperationalDetail` `onBack` + `useHrSafeBack` |
| B2 Pushed module/hiring lists missing Back | `HrPushedNav` on More modules; OperationalList `onBack` for candidates/interviews; People stack `showBack` |
| B3 Bare `router.back()` | `decideHrSafeBack` / `useHrSafeBack` — history → back, else replace canonical parent |
| B4 Signed-out stack leak | `AccessGate` mounts auth-only Stack (`sign-in`, `gestureEnabled: false`) when `signedOut` |

Gate: `apps/wathefni-employee-mobile/scripts/verify-hr-navigation-ergonomics.py`

Canonical parents live in `src/hr/navigation.ts` (`hrCanonicalParent`).

## SAFE POST-LAUNCH DEBT

| Item | Notes |
| --- | --- |
| Home `push` to Inbox/More | Still stacks tab siblings; prefer tab `navigate` |
| Cream vs legacy header chrome | Two visual languages remain; Back contract is shared |
| Duplicate People surface | Tab vs `/hr/employees` — stack copy now has Back |
| Physical device swipe/system-back matrix | Reconfirm on canary after OTA (iOS swipe + Android back) |
| RTL locale-before-native-flip timing | Shared i18n caveat; icon direction correct after reload |

## Not in scope this wave

Broad cream redesign of nested legacy screens · workflow changes · modal presentation changes.
