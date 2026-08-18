# OctoHR store-review and Google closed-test status

**Date:** 2026-08-18

**Branch:** `authority-cutover`

**Release commit:** `e025436d`

**Exact binaries:** iOS `0.3.1 (41)`; Android `0.3.1 (21)`

## Official store-review access

Production API qualification passed for the four fixed identities in the
synthetic `OCTOHR-STORE-REVIEW` tenant:

- Apple HR reviewer
- Apple Employee reviewer
- Google HR reviewer
- Google Employee reviewer

Observed production results:

- review-access kill switch: ON
- login: 4/4
- principal `/me`: 4/4
- tenant binding: 4/4
- distinct audit/session subjects: 4/4
- wrong-principal credentials: denied 4/4
- arbitrary identity: denied
- Employee data: Home, Schedule, Attendance, Leave, Payslips, Documents,
  Onboarding, Performance/OKRs, Talent, Learning, Benefits and Engagement all
  returned governed synthetic data
- HR data: Home/Inbox, Attendance, Leave, Shifts, Onboarding, Documents, Tasks
  and Performance all returned governed synthetic data

Passwords, bearer tokens and PINs are not recorded in repository evidence.
Owner-only credentials and handoff packs remain on production with mode 0600:

- `/root/.openclaw/secrets/octohr-store-review-owner.json`
- `/root/.openclaw/secrets/octohr-store-review-apple.txt`
- `/root/.openclaw/secrets/octohr-store-review-google.txt`

## Google Play closed-test tenant

The isolated synthetic `OCTOHR-CLOSED-TEST` tenant is provisioned through the
normal tenant-scoped HR authentication architecture. It contains 15 persistent
ordinary HR-mobile identities, one per external tester. It has no alternate
authentication route, Setup authority, user-management authority or
superadmin authority.

Observed production results:

- normal HR login: 15/15
- principal `/me`: 15/15
- tenant binding: 15/15
- wrong customer/review tenant: denied
- store-review adapter: denied
- `settings.manage`: absent
- `users.manage`: absent
- governed synthetic data present: Home/Inbox, People, Hiring, Attendance,
  Leave, Shifts, Onboarding, Documents, Tasks and Performance

Owner-only credentials and tester handoff remain on production with mode 0600:

- `/root/.openclaw/secrets/octohr-closed-test-owner.json`
- `/root/.openclaw/secrets/octohr-closed-test-testers.txt`
- `/root/.openclaw/secrets/octohr-closed-test-report.json`

## Google Play Closed Testing track

- package: `ai.wathefni.employee`
- track: Closed testing / Alpha (`4699006782633145065`)
- release: `21 (0.3.1)` promoted from Internal Testing
- status: draft; not publicly released
- countries/regions: all available countries targeted, so tester account
  countries are covered while access remains group-gated
- tester Google Group: not configured because the current Testers Community
  address has not been independently verified
- opt-in link: unavailable until the verified group is configured and the
  closed release is published

No production/public track was changed.

## Exact-binary qualification

Exact-binary physical UI qualification is **not complete**. The production API
and authorization results above do not prove rendered behavior, local PIN/lock,
principal switching or installed-app deep-link routing on iOS 41 and Android
21. No Android device is attached to the host, and the host's selected Apple
developer tools cannot operate the connected iPhone build.

Consequently, no exact-binary PASS and no full mobile release stamp is issued
by this record.

## Remaining owner-dependent blockers

1. Supply the exact current Testers Community Google Group address from their
   account/setup instructions. Do not infer it from an old message or search
   result.
2. Execute/observe the official reviewer flows on installed iOS 0.3.1 (41) and
   Android 0.3.1 (21): HR and Employee login, both switch directions, distinct
   local PIN/lock behavior, representative modules, HTTPS deep links, branding
   and `api.octo-hr.com` connectivity.
3. After the group is verified, configure it on the Closed Testing track,
   publish only that closed release, verify the opt-in page, and hand the link
   and per-tester instructions to Testers Community.
