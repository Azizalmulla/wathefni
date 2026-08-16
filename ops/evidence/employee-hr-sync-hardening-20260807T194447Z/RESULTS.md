# Employee↔HR Sync Hardening

- PASS: mobile softRefresh helper
- PASS: unlock dismiss soft-refreshes
- PASS: profile PTR refreshMe
- PASS: documents renew→onboarding invalidate
- PASS: HR inboundQueue freshness
- PASS: Leave soft poll
- PASS: Onboarding/Compliance/AppAccess soft poll
- PASS: Org ESS Reject
- PASS: Org ESS payroll gate
- PASS: catalog_label bilingual
- FAIL: employee /app/me 200 ({'detail': {'error': 'app_auth_failed', 'message': 'Please sign in again.'}})
- FAIL: employee /app/me re-fetch stable ({'detail': {'error': 'app_auth_failed', 'message': 'Please sign in again.'}})
- PASS: profile fields present after re-fetch
- FAIL: notifications EN ({'detail': {'error': 'app_auth_failed', 'message': 'Please sign in again.'}})
- FAIL: notifications AR ({'detail': {'error': 'app_auth_failed', 'message': 'Please sign in again.'}})
- FAIL: employee onboarding readable-or-gated ({'detail': {'error': 'app_auth_failed', 'message': 'Please sign in again.'}})
- FAIL: employee leave readable-or-gated ({'detail': {'error': 'app_auth_failed', 'message': 'Please sign in again.'}})
- FAIL: employee documents readable-or-gated ({'detail': {'error': 'app_auth_failed', 'message': 'Please sign in again.'}})
- FAIL: employee shifts readable-or-gated ({'detail': {'error': 'app_auth_failed', 'message': 'Please sign in again.'}})
- PASS: HR leave queue
- PASS: HR onboarding queue
- PASS: HR compliance queue
- PASS: HR app access/invitation

Required: 15/23 · overall=FAIL
