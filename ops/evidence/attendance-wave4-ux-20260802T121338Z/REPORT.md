# Attendance Wave 4 — UX refinement & staging qualification

**Stamp:** `20260802T121338Z`  
**Evidence:** `ops/evidence/attendance-wave4-ux-20260802T121338Z/`  
**Scope:** local + staging only. Production `/var/www` **not** changed.  
**Hard bans held:** `CAPTURE_INGEST=off`; no biometric / QR / GPS / kiosk / broad clocking; no real payroll money impact.

---

## Separate verdicts

| Gate | Verdict |
|---|---|
| **Staging UX (WATHEFNI synthetic)** | **GO (conditional)** — ops queue, connector health, EN/AR × desktop/mobile authenticated screenshots green; ops API smoke **55/55** (freeze skipped in nested run; E360 freeze **57/57** standalone) |
| **Production UX deployment** | **NO-GO** — staging-only promote; no production dashboard or flag change in this pack |
| **Controlled real HR attendance operations** | **NO-GO** — synthetic / lab only; do not put live employee days through this UX as the system of record yet |
| **Real punch ingest / devices / QR / GPS / kiosk** | **NO-GO** |
| **Real payroll money impact** | **NO-GO** |

---

## Page-by-page audit

See [`audit/page-by-page.md`](audit/page-by-page.md).

---

## Implemented UX changes

| Area | Change |
|---|---|
| Ops queue | `AttendanceOpsPanel.tsx` — exceptions, corrections, disputes, locked; owner/due/next; payroll BlockedReason |
| Daily board | `AttendanceDailyBoard.tsx` — overview stats + enriched table + day detail expand |
| Helpers | `attendanceUx.ts` — life states, EN/AR labels, payroll exclusion copy |
| Capture health | `AttendanceCaptureOps.tsx` — **Connector health** customer copy; ingest-off retained |
| Page shell | `PostHire.tsx` AttendancePage — bilingual RTL, mounts ops + capture + daily board |
| API | `api.ts` — `/dashboard/attendance/ops/*` clients |
| Backend | `list_queue` returns durable `cases` + `disputes` for UI reload |

Bundle markers (`tests/bundle-markers.txt`): Attendance operations / عمليات الحضور / Connector health / Day detail / Approved — ready to apply / Payroll excluded present.  
PostHire chunk: `PostHire-D8YjEnpm.js` sha256 `2f4cfd5303727e59839a180d7bac2d4a227b01703c25e3c102e0546e547ae5f6`.

---

## Tests & proofs

| Proof | Result |
|---|---|
| Local Wave 3 ops smoke | **56/56** (`tests/qualify-local.out`) |
| Local E360 freeze | **57/57** |
| Local Onboarding freeze | **54/54** |
| Staging ops smoke (no nested freeze) | **55/55** (`remote/tests/ops-smoke-nofreeze.out`) |
| Staging E360 freeze (standalone) | **57/57** |
| Unit `attendanceUx.test.ts` | **3/3** |
| Dashboard build | PASS |
| Staging dashboard path | `/opt/wathefni/staging/dashboard-dist` only (backup `*.bak-wave4-20260802T121338Z`) |
| Ingest flag | **off** |

Known staging note: nested onboarding freeze inside Wave 3 smoke can fail on staging app drift — see `docs/STAGING_ONBOARDING_FREEZE_DRIFT.md`. Local onboarding freeze remains green; not accepted as a new baseline.

---

## Screenshots (authenticated)

`screenshots/` — EN/AR × desktop/mobile:

- `attendance-overview-{en,ar}-{desktop,mobile}.png`
- `attendance-ops-{en,ar}-{desktop,mobile}.png`
- `connector-health-{en,ar}-{desktop,mobile}.png`

Manifest: `screenshots/manifest.json` (12 PNGs). Seed notes: capture ops seed ok; ops list returns `cases` key; one synthetic missing check-out exception with payroll exclusion visible.

---

## Remaining blockers

1. **Production UX not deployed** — requires explicit production promote + canary after staging soak.
2. **Daily table / day-detail visual proof thin** — today’s attendance list returned **0 rows** in the screenshot window (ops exception + connector lab data shown; enriched table columns need authority day rows in-range).
3. **Staging onboarding freeze drift** — pre-existing; local freeze green; do not treat staging fail as attendance UX regression.
4. **Interactive dual-approval / apply click-path** — covered by Wave 3 API smoke; full UI click-through soak still recommended before production UX GO.
5. **Employees 360 org-unit UI** still contains legacy “Wave 4” product strings (frozen module — out of scope to rewrite here).

---

## GO / NO-GO summary

- **GO** to keep iterating and soaking **staging** Attendance UX for WATHEFNI synthetic ops (ingest remains off).
- **NO-GO** for **production UX deployment**.
- **NO-GO** for **controlled real HR attendance operations** as customer-facing production workflow.
- **NO-GO** for real punch ingestion, devices, QR, GPS, kiosk, or real payroll money impact.
