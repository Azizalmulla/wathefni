# Employee Mobile — Navigation ergonomics debt

Stamp: after E1–E7 remediation (safe-back contract).

## Fixed (do not reopen without product change)

| Item | Resolution |
| --- | --- |
| E1 Shared safe-back | `employeeCanonicalParent` / `decideEmployeeSafeBack` / `useEmployeeSafeBack` |
| E2 Bare `router.back()` on pushed routes | Wired Settings, Documents, Bank, Onboarding, Leave request, Privacy, Change PIN, Inbox, histories |
| E3 Loading/error omit Back | `EmployeePushedEscape` + onBack on Bank/Onboarding loading/error |
| E4 Bank unavailable bare back | Uses `useEmployeeSafeBack` + PageBackButton chrome |
| E5 Change PIN blank | Never `return null`; escape to Settings; Cancel uses safe-back |
| E6 Payslip Android back | `BackHandler` closes in-page detail before leaving tab |
| E7 Signed-out stack leak | AuthGate mounts auth-only Stack (`(auth)`, `gestureEnabled: false`) |

Gate: `apps/wathefni-employee-mobile/scripts/verify-employee-navigation-ergonomics.py`

## SAFE POST-LAUNCH DEBT (unchanged)

| Item | Notes |
| --- | --- |
| D1 Payslips FeatureUnavailable `onRefresh={() => router.back()}` | Prefer `refreshMe`; Back Home still works |
| D2 Change PIN Cancel text vs PageBack chrome | Dismiss exists; chrome inconsistent |
| D3 Physical swipe/system-back matrix | Reconfirm on canary after OTA |
| D4 RTL locale-before-native-flip timing | Shared i18n caveat; icon direction correct |

## Not in scope

Broad redesign · Home push→tab navigate · workflow changes.
