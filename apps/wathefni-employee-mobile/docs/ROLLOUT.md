# Employee App — rollout runbook

The app and its backend are **inert by default**. Two independent gates must both
be on for any employee to use it:

1. Master flag `WATHEFNI_EMPLOYEE_APP` (env, default OFF) — gates the whole `/app/*`
   surface and the push channel control flag `WATHEFNI_PUSH_NOTIFICATIONS`.
2. Per-company module `employee_app` in `company_modules` (default absent) — gates
   which companies can activate.

Nothing in this change enables anything in production. The steps below are the
deliberate, staged path to switch it on.

## Stage 0 — internal dev

- `EXPO_PUBLIC_API_BASE_URL` → staging. Run against staging with both gates ON
  for one internal test company.
- Verify the staging smoke suite is green (includes `smoke-test-employee-app.py`):
  `ops/deploy.sh staging`.

## Stage 1 — closed internal QA

- Build internal clients: `eas build --profile preview --platform all`.
- iOS TestFlight internal track + Android internal testing track, small group
  (team + a few consenting employees), still pointed at staging.
- Exercise: activation (HR issues a code), push receipt vs. fallback, leave
  request/cancel, document upload, onboarding checklist, offboarding revoke.

## Stage 2 — pilot company (production, flag-gated)

Promote backend code first (additive, gates OFF):

```bash
cd wathefni-orchestrator
ops/deploy.sh staging        # green, records staging-green hash
ops/deploy.sh production     # ships /app/* code with all gates still OFF
```

Then enable for EXACTLY ONE pilot company:

```bash
# 1) Backend master flags via systemd drop-in (mirrors prior feature rollouts)
#    /etc/systemd/system/wathefni-orchestrator.service.d/employee-app.conf
#      [Service]
#      Environment=WATHEFNI_EMPLOYEE_APP=on
#      Environment=WATHEFNI_PUSH_NOTIFICATIONS=on
#      # optional: Environment=WATHEFNI_EXPO_ACCESS_TOKEN=...   (enhanced push security)
systemctl daemon-reload && systemctl restart wathefni-orchestrator.service

# 2) Enable the module for the pilot company only
#    INSERT INTO company_modules (company_code, module_key, enabled, source)
#    VALUES ('PILOTCO','employee_app',TRUE,'pilot')
#    ON CONFLICT (company_code, module_key) DO UPDATE SET enabled=TRUE;
```

- Production app build: `eas build --profile production` + `eas submit`. Limit
  TestFlight external / Play closed testing to the pilot company's employees.
- HR issues activation codes from the dashboard (`POST /dashboard/posthire/employees/{key}/app-invite`).

### Monitor during pilot

- Activation success rate (`employee_app_invites` redeemed vs. issued/locked).
- Push delivery vs. fallback mix (`outbound_delivery_events` channel=push;
  `employee_messages` status by flow).
- `hr_tasks` volume (activation codes that reached nobody; account-deletion requests).
- Crash-free sessions (Expo/EAS).

## Stage 3 — expand

- Enable the `employee_app` module for more companies once the pilot is stable.
- The master flags stay on; per-company control remains the `company_modules` row.

## Stage 4 — public listing

- Move to public App Store / Play Store listings. Safe because activation still
  requires an HR-issued, company-scoped code — public listing is **not** open
  self-registration.

## Rollback

- Per company: set the `employee_app` module row `enabled=FALSE`.
- Global: remove the drop-in (`WATHEFNI_EMPLOYEE_APP`) and restart — every `/app/*`
  route returns 503 and the app shows "not available", with zero impact on the
  dashboard or existing WhatsApp/email delivery.
