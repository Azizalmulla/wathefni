# Store submission & review checklist (App Store + Play Store)

Pre-submission checklist for the OctoHR Employee App. Owner: release manager.

## Blockers (must be done before any testing track)

- [ ] Publish the privacy policy (see `PRIVACY.md`) at a stable public URL and set
      it in `app/settings.tsx` (`PRIVACY_URL`) and both store listings.
- [ ] Set a real EAS `projectId` in `app.json` (`extra.eas.projectId`). Without it
      push registration is disabled (app still works via the inbox).
- [ ] App icon + splash assets added (Expo defaults are placeholders).
- [ ] Confirm `EXPO_PUBLIC_API_BASE_URL` per build profile in `eas.json`.

## Account deletion (Apple 5.1.1(v) + Google Play)

- Implemented: Settings → "Request account deletion" → `POST /app/account/request-deletion`,
  which raises a visible HR task. The employer is the data controller, so the
  in-app action routes a deletion **request** to HR rather than self-destructing
  employment records. Document this rationale in the review notes.

## Permissions justification (for App Privacy / Data Safety forms)

| Permission | When requested | Justification |
|---|---|---|
| Notifications | First sign-in / Settings toggle | Deliver HR reminders. App fully usable if denied (in-app inbox). |
| Camera | Only on "Upload document" | Capture a document the employee chooses to submit to HR. |
| Photos / Files | Only on "Upload document" | Attach an existing document the employee chooses to submit. |

No location, contacts, microphone, background location, or advertising ID.

### Data collected / linked to the user (declare as collected, linked, not for tracking)

- Contact info: name, phone number.
- User content: documents the user uploads.
- Employment/HR data surfaced via the API (onboarding, shifts, attendance, leave).
- Identifiers: push token, device platform/app version.
- Purpose: app functionality only. Not used for tracking. Not shared for ads.

## Review notes to include in the submission

- This is an employer-provisioned B2B app. Accounts are created by the employee's
  HR team, who issue a one-time activation code; there is no open self-registration.
- Reviewer access: provide a demo company + a test phone number and a freshly
  issued activation code (generate from the dashboard "Invite to App"), valid for
  24h. Re-issue if it expires during review.
- The app is native screens (not a web wrapper).
- Push is optional; deny the permission and the in-app inbox still shows everything.

## Common rejection risks (mitigations in place)

- Account deletion path — present (see above).
- Permission prompts without context — permissions are requested just-in-time at
  the relevant action; usage strings are set in `app.json` infoPlist / Android
  permissions.
- Login wall with no way in for the reviewer — mitigated by the demo-code note above.
- Debug logging — `console.*` is stripped from production builds (`babel.config.js`).
- Sign in with Apple — not required (phone + code is not third-party SSO).

## Build & submit

```bash
eas build --profile production --platform all
eas submit --profile production --platform all
```
Then: iOS → TestFlight (internal first, then external beta review for the pilot
company's testers); Android → Play internal testing → closed testing for the pilot.
