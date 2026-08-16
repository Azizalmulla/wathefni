# HR mobile terminal qualification — 20260811T091247Z

**Ship (terminal):** `NO-SHIP`
**Reason:** FAIL=7 PASS=72 SKIP=5 — terminal API/contract only; PHYSICAL_ONLY remains for device UI

## Counts

| Verdict | Count |
| --- | ---: |
| FAIL | 7 |
| PASS | 72 |
| SKIP | 5 |

## Matrix

| Surface | CTA / deep link | API / action | Expected | Actual | Verdict |
| --- | --- | --- | --- | --- | --- |
| Static/routes | app/hr/** route tree | `expo file-based routes` | registered HR screens | 28 routes | **PASS** |
| Static/destinationAvailable | /leave/ | `capabilities.destinationAvailable` | gated | present | **PASS** |
| Static/destinationAvailable | /candidates/ | `capabilities.destinationAvailable` | gated | present | **PASS** |
| Static/destinationAvailable | /onboarding/ | `capabilities.destinationAvailable` | gated | present | **PASS** |
| Static/destinationAvailable | /employees/ | `capabilities.destinationAvailable` | gated | present | **PASS** |
| Static/destinationAvailable | /shift-swaps/ | `capabilities.destinationAvailable` | gated | present | **PASS** |
| Static/destinationAvailable | /interviews/ | `capabilities.destinationAvailable` | gated | present | **PASS** |
| Static/destinationAvailable | /tasks/ | `capabilities.destinationAvailable` | gated | present | **PASS** |
| Static/destinationAvailable | /documents/ | `capabilities.destinationAvailable` | gated | present | **PASS** |
| Static/destinationAvailable | /attendance/ | `capabilities.destinationAvailable` | gated | present | **PASS** |
| Static/destinationAvailable | /assistant | `capabilities.destinationAvailable` | gated | present | **PASS** |
| Static/assistantDeepLinks | page=leave | `mapAssistantNavigation` | mapped or web-only refused | mapped | **PASS** |
| Static/assistantDeepLinks | page=attendance | `mapAssistantNavigation` | mapped or web-only refused | mapped | **PASS** |
| Static/assistantDeepLinks | page=shifts | `mapAssistantNavigation` | mapped or web-only refused | mapped | **PASS** |
| Static/assistantDeepLinks | page=onboarding | `mapAssistantNavigation` | mapped or web-only refused | mapped | **PASS** |
| Static/assistantDeepLinks | page=candidates | `mapAssistantNavigation` | mapped or web-only refused | mapped | **PASS** |
| Static/assistantDeepLinks | page=interviews | `mapAssistantNavigation` | mapped or web-only refused | mapped | **PASS** |
| Static/assistantDeepLinks | page=tasks | `mapAssistantNavigation` | mapped or web-only refused | mapped | **PASS** |
| Static/assistantDeepLinks | page=documents | `mapAssistantNavigation` | mapped or web-only refused | mapped | **PASS** |
| Static/assistantDeepLinks | page=jobs | `mapAssistantNavigation` | mapped or web-only refused | mapped | **PASS** |
| Static/handlers | request('/dashboard/mobile/…') crawl | `0 unique API paths` | >=15 mobile endpoints referenced | 0 | **FAIL** |
| Static/safe-back | cold-start parent of /hr/leave/abc | `hrCanonicalParent` | /hr | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/candidates/x | `hrCanonicalParent` | /hr/candidates | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/candidates | `hrCanonicalParent` | /hr/hiring | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/jobs | `hrCanonicalParent` | /hr/hiring | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/interviews/i1 | `hrCanonicalParent` | /hr/interviews | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/interviews | `hrCanonicalParent` | /hr/hiring | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/employees/e1 | `hrCanonicalParent` | /hr/people | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/employees | `hrCanonicalParent` | /hr/more | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/tasks/t1 | `hrCanonicalParent` | /hr/tasks | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/tasks | `hrCanonicalParent` | /hr/more | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/onboarding/e1 | `hrCanonicalParent` | /hr/onboarding | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/onboarding | `hrCanonicalParent` | /hr/more | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/documents/e1/civil_id | `hrCanonicalParent` | /hr/documents | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/documents | `hrCanonicalParent` | /hr/more | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/attendance/a1 | `hrCanonicalParent` | /hr/attendance | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/attendance | `hrCanonicalParent` | /hr/more | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/shift-swaps/s1 | `hrCanonicalParent` | /hr/shifts | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/shifts | `hrCanonicalParent` | /hr/more | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/delivery-alerts | `hrCanonicalParent` | /hr/more | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/assistant | `hrCanonicalParent` | /hr/more | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/settings | `hrCanonicalParent` | /hr/more | implemented | **PASS** |
| Static/safe-back | cold-start parent of /hr/change-pin | `hrCanonicalParent` | /hr/settings | implemented | **PASS** |
| Static/i18n | 458 HR-related t() keys | `en.json ∩ ar.json` | all keys present EN+AR | missing_en=17 missing_ar=17 | **FAIL** |
| Auth | Work email Sign in | `POST /dashboard/mobile/auth/login` | access_token + me | ok | **PASS** |
| Auth | Session /me | `GET /dashboard/mobile/me` | HTTP [200] | HTTP 200 | **PASS** |
| Home | Home priorities | `GET /dashboard/mobile/priorities` | HTTP [200] | HTTP 200 | **PASS** |
| Leave | Leave requested list | `GET /dashboard/mobile/leave?status=requested&limit=10` | HTTP [200] | HTTP 200 | **PASS** |
| People | Employee search | `GET /dashboard/mobile/employees?limit=10` | HTTP [200] | HTTP 403 | **FAIL** |
| People | Employee profile (Talal canary) | `GET /dashboard/mobile/employees/WATHEFNI-96550252254` | HTTP [200] | HTTP 403 | **FAIL** |
| Shifts | Today shifts | `GET /dashboard/mobile/shifts?date=2026-08-11` | HTTP [200] | HTTP 200 | **PASS** |
| Delivery Alerts | Open Delivery Alerts | `GET /dashboard/mobile/delivery-alerts` | HTTP [200] | HTTP 200 | **PASS** |
| Assistant | Assistant capabilities | `GET /dashboard/mobile/assistant/capabilities?locale=en` | HTTP [200] | HTTP 200 | **PASS** |
| Assistant | Assistant capabilities AR | `GET /dashboard/mobile/assistant/capabilities?locale=ar` | HTTP [200] | HTTP 200 | **PASS** |
| Hiring | Jobs / positions | `GET /dashboard/mobile/positions?status=open&limit=10` | HTTP [200] | HTTP 200 | **PASS** |
| Hiring | Unscoped candidates list | `GET /candidates (no position)` | honest requires_position / ranking_unavailable (not fake empty success) | HTTP 200 keys=ok,items,total,filters,ai_advisory,ranking_unavailable,ranking_error,requires_position items=0 total=0 | **PASS** |
| Hiring | Candidates for position OCCTST_044035 | `GET /dashboard/mobile/candidates?position=OCCTST_044035&limit=10` | HTTP [200] | HTTP 200 | **PASS** |
| Interviews | Interviews list | `GET /dashboard/mobile/interviews` | HTTP [200] | HTTP 200 | **PASS** |
| Leave | provision disposable fixtures | `SSH leave_requests INSERT` | two requested leaves | Expecting property name enclosed in double quotes: line 1 column 2 (char 1) | **FAIL** |
| Attendance | Open Attendance queue | `GET /dashboard/mobile/attendance?status=unresolved&limit=5` | HTTP [200] | HTTP 400 | **FAIL** |
| Attendance | Mutation prepare | `no unresolved exceptions` | skip without inventing fixtures | empty queue | **SKIP** |
| Shifts | Open shift-swap queue | `GET /dashboard/mobile/shift-swaps?status=requested&limit=5` | HTTP [200] | HTTP 200 | **PASS** |
| Shifts | Swap mutation | `no requested swaps` | skip | empty | **SKIP** |
| HR Tasks | Open Tasks | `GET /dashboard/mobile/tasks?status=open&limit=5` | HTTP [200] | HTTP 200 | **PASS** |
| HR Tasks | Open task detail | `GET /dashboard/mobile/tasks/2d51a053-fa7e-4eed-bacd-dc14e1b842ec` | HTTP [200] | HTTP 200 | **PASS** |
| HR Tasks | Mark done | `POST /tasks/{id}/resolve` | not executed — no disposable task fixture yet | SKIPPED_NO_DISPOSABLE_FIXTURE | **SKIP** |
| Onboarding | Open Onboarding | `GET /dashboard/mobile/onboarding?limit=5` | HTTP [200] | HTTP 200 | **PASS** |
| Onboarding | Open employee onboarding | `GET /dashboard/mobile/onboarding/WATHEFNI-96597727743` | HTTP [200] | HTTP 200 | **PASS** |
| Onboarding | Accept/Waive | `POST /onboarding/{key}/review` | not confirmed without disposable item | SKIPPED_NO_DISPOSABLE_FIXTURE | **SKIP** |
| Documents | Open Documents needs_review | `GET /dashboard/mobile/documents?status=needs_review&limit=5` | HTTP [200] | HTTP 200 | **PASS** |
| Documents | Mark reviewed | `POST /documents/.../review` | not confirmed without disposable item | SKIPPED_NO_DISPOSABLE_FIXTURE | **SKIP** |
| Documents/Files | Unauthenticated GET /dashboard/mobile/documents/files/4d91ab7c-e9e4-4b67-8ebc-637032424e70 | `auth gate` | 401/403 | HTTP 401 | **PASS** |
| Documents/Files | Authenticated GET /dashboard/mobile/documents/files/4d91ab7c-e9e4-4b67-8ebc-637032424e70 | `file bytes / JSON error` | 200 file or honest 404 | HTTP 200 | **PASS** |
| Documents/Files | Unauthenticated GET /dashboard/mobile/documents/files/4d91ab7c-e9e4-4b67-8ebc-637032424e70?disposition=attachment | `auth gate` | 401/403 | HTTP 401 | **PASS** |
| Documents/Files | Authenticated GET /dashboard/mobile/documents/files/4d91ab7c-e9e4-4b67-8ebc-637032424e70?disposition=attachment | `file bytes / JSON error` | 200 file or honest 404 | HTTP 200 | **PASS** |
| Documents/Files | Unauthenticated GET /dashboard/mobile/documents/files/8572a0f2-ceaf-4991-aa8f-7f673095105a | `auth gate` | 401/403 | HTTP 401 | **PASS** |
| Documents/Files | Authenticated GET /dashboard/mobile/documents/files/8572a0f2-ceaf-4991-aa8f-7f673095105a | `file bytes / JSON error` | 200 file or honest 404 | HTTP 200 | **PASS** |
| RBAC/Tenant | Foreign/unknown leave detail | `GET /leave/00000000-0000-0000-0000-000000000099` | 404/403 not 200 with foreign payload | HTTP 404 | **PASS** |
| RBAC/Tenant | Bogus confirm | `POST /leave/{fake}/decision confirm=true` | 4xx fail closed | HTTP 404 | **PASS** |
| Assistant | Capabilities payload | `GET /assistant/capabilities` | 200 with tools/pages | HTTP 200 keys=ok,company_code,catalog,empty_state,surface,unsupported_messaging | **PASS** |
| Assistant | Refuse web-only page=assessments | `WEB_ONLY_PAGES` | not linked on mobile | listed | **PASS** |
| Assistant | Refuse web-only page=reports | `WEB_ONLY_PAGES` | not linked on mobile | listed | **PASS** |
| Assistant | Refuse web-only page=calendar | `WEB_ONLY_PAGES` | not linked on mobile | listed | **PASS** |
| Leave | Fixture cleanup | `cleanup` | cleanup ok | Expecting property name enclosed in double quotes: line 1 column 2 (char 1) | **FAIL** |

## PHYSICAL_ONLY

- Real-device tap hit-testing / XCTest clickable (BrowserStack Maestro)
- Face ID / Touch ID biometric unlock and opt-in sheet
- Keyboard occlusion, scroll physics, sheet gesture dismiss
- RTL visual mirroring and Back chevron direction on device
- Native PDF/image previewer rendering (HTTP file gate is terminal-proven)
- Push notification banner → deep link cold start on physical device
- Offline/cache visual empty/error chrome timing
