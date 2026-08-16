# HR mobile IA foundation — architecture

**Stamp:** provisional IA agreed 2026-08-09  
**Scope:** shell + sparse Home only (modules unchanged)

## Screen hierarchy

```
/hr/sign-in                          (unsigned)
/hr/(tabs)                           (signed-in shell)
  /hr/(tabs)/index                   Home
  /hr/(tabs)/people                  People → employees list
  /hr/(tabs)/inbox                   Inbox → decision queue
  /hr/(tabs)/hiring                  Hiring → recruiting priorities + browse
  /hr/(tabs)/more                    More → grouped module access
/hr/employees/[employeeKey]          People hub detail (stack)
/hr/leave/[id]                       … existing module routes preserved
/hr/onboarding/…
/hr/documents/…
/hr/attendance/…
/hr/shifts
/hr/shift-swaps/[swapId]
/hr/tasks
/hr/candidates/…
/hr/interviews/…
/hr/delivery-alerts
/hr/settings
```

## Route mapping (tabs → authority)

| Tab | Route | Capability gate | Data |
| --- | --- | --- | --- |
| Home | `(tabs)/index` | always when signed in | `/priorities` filtered to ops sections; cap 6 |
| People | `(tabs)/people` | `employee_search` \| `employee_quick_profile` | existing employees list |
| Inbox | `(tabs)/inbox` | leave \| onboarding \| attendance \| documents \| swaps | `/priorities` decision sections only |
| Hiring | `(tabs)/hiring` | recruiting workspace + candidate/interview features | `/priorities` prehire + candidate_decisions; browse links |
| More | `(tabs)/more` | always | capability-filtered grouped links + settings |

## Inbox allowlist (not a notification dump)

**In:** `leave_approvals`, `onboarding_reviews`, `attendance_exceptions`, `document_reviews`, `shift_swap_decisions`  
**Out:** `delivery_alerts` (→ More), `prehire_priorities` / `candidate_decisions` (→ Hiring), generic alerts

## Home allowlist

Ops only: leave, onboarding, attendance, hr_tasks, document_reviews, shift_swap_decisions.  
Hiring never on Home.

## AI Recruiter

No sixth tab. Rankings/evidence remain on candidate detail (`/hr/candidates/[appKey]`). Hiring tab browse → Candidates.

## Component reuse from Employee

| Reuse | Source |
| --- | --- |
| Tab bar chrome | `colors.ink`, `layout.tabBarBase`, `radius.xl`, active/inactive tints |
| Tab haptics | `@/native/haptics` `tabFeedback` |
| Page geometry | `@/theme` `layout.pageMargin`, `scrollBottom`, cream `colors.bg` |
| Capability-hide tabs | same `href: null` pattern as Employee `(tabs)/_layout` |

Not reused yet (avoid employee I18n/Auth coupling): Wordmark, HomeView, Employee cards.

## Less-is-more rules enforced

- No module ActionableCard grid on Home
- Tabs capability-gated (disappear when off)
- More is quiet rows, not sidebar
- No invented urgency — priorities API only
