# Attendance Wave 2E — Production dark deploy + capture-operations UI

**Stamp:** `20260802T031411Z`  
**Mode:** Production DARK. No real customer device. No real punch ingest. QR/GPS/kiosk off. Wave 1 authority remains synthetic-only. Frozen Employees 360 / Onboarding unchanged.

## Result

| Gate | Result |
|---|---|
| Staging E360 freeze (refreshed helpers) | **57/0** |
| Staging Onboarding freeze | Partial (app surface still skewed); **prod onboarding freeze 54/0** used as deploy gate |
| Prod E360 freeze | **57/0** |
| Prod Onboarding freeze | **54/0** |
| Prod dark canary | **30/0** |
| HTTP API parity (TestClient) | **PASS** (`HTTP_API_PARITY_OK`) |
| Leak scan (remote + local evidence) | **PASS** |
| Rollback prove + redeploy | **PASS** |
| Demo attendance rows | **42 unchanged** |

## Production flags (final)

```
WATHEFNI_ATTENDANCE_AUTHORITY=on
WATHEFNI_ATTENDANCE_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_ONLY=on
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_KEY_MARKERS=ATTW1C,ATTW2C,ATTW2E,W1C-SYNTH|,W2C-SYNTH|,W2E-SYNTH|
WATHEFNI_ATTENDANCE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965524
WATHEFNI_ATTENDANCE_AUTHORITY_STORE=postgres
WATHEFNI_ATTENDANCE_IMPORT=off
WATHEFNI_ATTENDANCE_CAPTURE_OPS=on
WATHEFNI_ATTENDANCE_CAPTURE_OPS_COMPANIES=WATHEFNI
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
EnvironmentFile=-/root/.openclaw/secrets/attendance-capture.env  (mode 600)
```

## Production SHAs (representative)

| Path | SHA256 |
|---|---|
| `app.py` | `481abf11c8ada15939e3796753c5693b22a6a175099beaaeb43e95261cc2bfb5` |
| `attendance_capture_ops.py` | `8c1a2eea90662158431fd5d142d47520e86d93a0677ceb3de0349a7942b941e6` |
| `attendance_capture_ops_http.py` | `4efc5400d97e66310e20e312b3f8c68825c941998427537ef70d91913602f603` |
| `dashboard-dist/index.html` | `bcaaf2cb087094fd33d7306df59b746b05c97f413fd0a285ea90724b3de60474` |

Full module list: `remote/verify/post-deploy-shas.txt`.

## Delivered

### Backend (dark)
- `attendance_capture_ops.py` — process service (registry/remediation/health/compat)
- `attendance_capture_ops_http.py` — `/dashboard/posthire/attendance/capture-ops*` APIs
- Flags: `CAPTURE_OPS=on`, `CAPTURE_INGEST=off`, import off, synthetic authority on
- Secrets only via EnvironmentFile; leak scan gates evidence
- Runbook + pilot checklist remain under `ops/`

### HR UI
- `AttendanceCaptureOps.tsx` on Attendance page (`?page=attendance`)
- Connector/site health, mapping / missing / conflict queues
- Approve / reject with stale-conflict messaging; Payroll-excluded badges
- EN/AR + RTL + mobile layout; loading / empty / error / permission states
- Punch replay blocked while ingest off

### Deploy / rollback
- `ops/deploy-attendance-wave2e-prod-dark.sh`
- Backup: `/opt/wathefni/backups/production-pre-attendance-wave2e-20260802T031411Z`
- `ROLLBACK.sh` proven → dropin removed → redeployed dark

## Screenshots

| File | Notes |
|---|---|
| `ui/capture-ops-en-desktop.png` | EN desktop fixture (mirrors panel contract) |
| `ui/capture-ops-en-mobile.png` | EN mobile viewport |
| `ui/capture-ops-ar-rtl.png` | AR/RTL panel present in fixture (desktop composite) |
| `ui/capture-ops-fixture.html` | Source fixture |

Live dashboard bundle deployed to `/opt/wathefni/dashboard-dist` (PostHire Attendance embeds the panel when `CAPTURE_OPS` is on).

## Remaining blockers

1. Staging onboarding freeze still incomplete vs local `app.py` helpers (prod freezes green)
2. Capture-ops state is process-local (resets on restart) — durable store needed before multi-node/pilot
3. Customer read-only BioTime compat against a real allowlisted site not yet run
4. HR UI screenshots are contract fixtures (not authenticated live browser session)
5. Real punch ingest / device connection still explicitly **off**

## Verdicts

| Question | Verdict |
|---|---|
| Dark connector production foundation | **GO** (synthetic/lab only) |
| HR capture-operations readiness | **CONDITIONAL GO** (UI+API dark live; durable store + live screenshot session pending) |
| Future customer read-only compatibility pilot | **CONDITIONAL GO** (probe API live; needs customer BioTime + checklist) |
| Real punch ingestion | **NO-GO** (`CAPTURE_INGEST=off`, import off, no real device) |

## Non-goals confirmed

No customer device · no real punches · no QR/GPS/kiosk · no freeze regressions on prod · Employees 360 / Onboarding frozen surfaces unchanged.
