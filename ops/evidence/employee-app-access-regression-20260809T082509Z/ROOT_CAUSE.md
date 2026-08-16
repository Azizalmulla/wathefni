# Access regression root cause — 20260809T082509Z

## Verdict: PASS (root cause proven · fix shipped · physical re-verify pending)

## Exact root cause

Not a Setup Console / entitlement / wrong-tenant disable.

After Aziz granted notification permission, `PushLifecycle` entered an infinite
`POST /app/push/register` loop (307 register lines in ~1 minute on production).

Drivers:
1. `addPushTokenListener` → `registerForPushToken` → listener fires again
2. Effect deps included unstable AuthProvider `request` → remount/re-run
3. Auto-register always used `requestPermission: true`

Storm exhausted the DB pool (`psycopg2.pool.PoolError: connection pool exhausted`).
`configured_company_modules()` swallowed that exception and fell through to legacy
file config **without** `employee_app`, so `company_has_module(..., "employee_app")`
returned False → `employee_app_context` returned **403**
`employee_app_not_enabled_for_company`.

Client `request()` called `blockForError(..., 'api')` for that soft code with
`blockApp: true` → shell projected **App access unavailable**.

## Why it surfaced now

Push UX wave made registration **auto** after OS permission (previously opt-in /
Settings-gated). First Allow on canary 0.2.0 triggered the new path.

## Push permission causal?

**Causal trigger, not entitlement change.** Permission itself did not disable the
company; it started auto-register, which stormed the API.

## Live entitlements (canonical — still enabled)

```json
{live}
```

Storm window counts (08:17–08:18 UTC): 307 register lines → 240×200, 11×403, 56×500.

`GET /app/me` flipped 200 → 403 during pool exhaustion; later 200 again.
7× `POST /app/auth/logout` during recovery — Try again may appear stuck if session
was cleared; re-activate if signed out.

## Try again

Calls `refreshMe()` only. Does not clear a false blocked state if `/app/me` still
returns the soft 403, and cannot recover a wiped session without OTP.

## Fix shipped

### Mobile (OTA canary runtime 0.2.0)
- `PushLifecycle`: requestRef, single-flight, lastRegisteredToken, ask permission once,
  listener never re-asks
- `authFailure`: soft access codes `blockApp: false` for `api` phase
- Gate: `scripts/verify-push-register-storm.py`

### Server (prod orchestrator restarted)
- `_is_transient_db_error` + re-raise from `configured_company_modules`
- `employee_app_context` → **503** `employee_app_temporarily_unavailable` instead of false 403
- Smoke: `smoke-test-employee-app-pool-entitlement.py`

### OTA
- Update group `754b9114-1b49-40db-93ce-127e33e65f09`

## Physical next (access only — no push event walk yet)

1. Force-quit Wathefni, reopen (pull OTA)
2. If still on access screen: Sign out → re-activate with OTP
3. Confirm Home loads with company WATHEFNI / Aziz canary
4. Confirm notification permission already granted does **not** return access screen
5. Only then resume push physical testing
