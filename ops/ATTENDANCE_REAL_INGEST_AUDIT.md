# Attendance Real-Ingest Audit

**Mode:** research + architecture only — **no** code, deploy, device connect, clocking enablement, or Attendance freeze reopen  
**Date:** 2026-08-03  
**Authority freeze:** `ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` (`20260802T131146Z`)  
**Prior architecture:** Wave 2A Kuwait device ecosystem (`ops/evidence/attendance-wave2a-kuwait-device-architecture-20260802T024341Z/`)  
**Pilot ops:** `ops/ATTENDANCE_PILOT_INSTALLATION_CHECKLIST.md` · `ops/ATTENDANCE_CONNECTOR_SECRET_RUNBOOK.md`

---

## Verdict in one line

**Long-term:** vendor-neutral **canonical ingest API/contract** + thin adapters (not a device SDK farm). **First strategy:** ZKTeco **BioTime pull + on-prem agent** (already built, production-dark). **First ingest wave:** **CONDITIONAL GO** as owner-approved **enablement + single-device pilot qualify** — not a rebuild; **NO-GO** to flip `CAPTURE_INGEST` without that wave.

---

## 1. Current product truth

### Architecture (frozen layers)

```
Devices / BioTime / CSV drop
        ↓
Capture: sanitize → map device_user_id → employee_key → quarantine/remediate
        ↓  (BLOCKED: CAPTURE_INGEST=off)
Authority: immutable punches → day projection → approve_day → payroll eligibility snapshot
        ↓
Ops: exception / correction / dual approve / apply ≠ approve
        ↓
Payroll: snapshots only — NO money posting
```

| Layer | Prod posture |
|---|---|
| Capture ops (registry, health, remediation UX) | **on** (dark/lab) |
| Capture ingest | **off** |
| Import V1 (dashboard CSV) | **off** |
| Authority + Ops | **on**, `SYNTHETIC_ONLY=on` |
| HR/manager UX | **GO** synthetic-backed |
| Real clocking / QR / GPS / kiosk | **NO-GO** |

### Ingest paths

| Path | Code | Prod |
|---|---|---|
| BioTime REST pull + agent outbox | Built (Wave 2B–2G) | Dark / ingest off |
| CSV / XLSX capture contract | Built | Off |
| Import V1 upload | Built | `IMPORT=off` |
| WhatsApp/tool punches | Authority hooks | Synthetic-gated only |
| HikCentral / BioStar / Anviz / IBA / ADMS | Researched (2A) | **Not built** |
| QR / GPS / kiosk / employee-app clock | Contract enums only | **NO-GO** |

### Identity, duplicates, offline, time

- **Match:** strict `device_user_id` / `emp_code` → `employee_key` mapping. No phone/name/biometric auto-match. Unknown → quarantine. Never auto-create employees.
- **Duplicates:** authority `UNIQUE (company, source, source_event_id)`; BioTime `biotime:{transaction_id}`; CSV content digests; import 2-minute window.
- **Offline:** agent sqlite outbox + retries + checkpoint; device/BioTime buffers remain vendor-side.
- **Timezone:** Asia/Kuwait default; naive times assumed Kuwait.
- **Clock drift:** pilot checklist NTP skew **&lt; 30s**; hard skew-quarantine is intent, not a proven hard production gate — tighten in any enablement wave.
- **Privacy:** biometric templates/images **hard-fail**; GPS scalars may appear as metadata only — not a GPS clocking product.

### Exception → approved authority

1. **Capture remediation** (pre-authority): unknown employee, duplicate conflict, connector lag/offline — map approve; **replay blocked while ingest off**.
2. **Ops exceptions** (post-projection): missing in/out, absence, lateness, early leave, etc. — review → dual where configured → **apply** creates new projection version (punches never rewritten).
3. **`approve_day`** requires clean exception state; payroll snapshot only when approved + eligible — incomplete days stay **payroll_excluded**.

### Payroll separation

Attendance may produce **eligibility snapshots** only. Freeze + Payroll freezes forbid real money, WPS/bank, and Attendance→Payroll calculation expansion from ingest.

---

## 2. Kuwait / GCC workflows and vendors

| Pattern | Reality |
|---|---|
| SME office / retail | ZKTeco terminals → BioTime private cloud → Excel/HRIS export |
| Multi-vendor corporates | IBA (KCS Kuwait) as T&A front regardless of reader brand |
| Security / Hik stacks | Hikvision + HikCentral / ISAPI |
| Suprema campuses | BioStar 2 TA API |
| SMB cloud | Anviz CrossChex webhooks |
| Fallback everywhere | USB / CSV / SFTP nightly |

Competitors (ZenHR, Bayzat, AiTIME class) sell **ZKTeco/BioTime native sync + mobile GPS/QR + attendance→payroll**. That is table-stakes commercial packaging. Wathefni must not copy “GPS/QR + payroll money” as the first move.

---

## 3. Build connectors vs generic API vs partners

| Option | Role |
|---|---|
| **Generic canonical ingest API/contract** | **Long-term core** — already the Wave 2 architecture. One sanitize/map/idempotency/privacy path. |
| **First-party BioTime + agent** | **First supported strategy** — already built; highest Kuwait share; event-only; no templates. |
| **CSV/SFTP adapter** | Same contract; covers USB exports and non-API sites. |
| **Partner / later adapters** | Hik, Suprema, Anviz, IBA — build only on deal evidence; prefer partner disclosure (IBA) over guessing. |
| **Do not** | Farm every terminal SDK; ADMS direct as default (biometric exfil risk); employee GPS/QR as first commercial path. |

**Best long-term:** Wathefni owns the **authority + exception + evidence** layer; connectors are **thin adapters** to the canonical envelope; device biometrics stay on vendor hardware/middleware.

---

## 4. Table-stakes vs differentiation

### Table-stakes (competitors already claim)

- ZKTeco / BioTime sync  
- Mobile GPS / QR clocking  
- Multi-branch attendance  
- Attendance feeds payroll OT/WPS stories  

### Genuine differentiation (keep)

1. **Immutable punch ledger + versioned day projections** — corrections never rewrite punches.  
2. **Approve ≠ apply** and dual approval for high-risk kinds.  
3. **Strict identity mapping + quarantine** — no fuzzy name match creating ghost employees.  
4. **Privacy hard-fail on biometric payloads** — device remains biometric authority.  
5. **Payroll exclusion honesty** until day is clean — no silent money from dirty punches.  
6. **Fail-closed capture ops** (secrets sealed, tenant SN ownership, kill ingest independently of UX).

### Do not claim

- “Any device, plug and play”  
- Legal compliance from GPS alone  
- Automated payroll money from punches  
- AI anomaly scheduling  

---

## 5. Exact first device / connector strategy

**Name:** ZKTeco **BioTime / ZKBio Time** transaction pull  
**Deploy:** On-prem agent (LAN → BioTime; outbound TLS → Wathefni)  
**Idempotency:** `source=biotime`, `source_event_id=biotime:{transaction_id}`  
**Scope:** **One customer · one site · one `terminal_sn`**  
**Fallback:** CSV capture for the same site if API license missing  
**Explicitly not first:** Hik, BioStar, Anviz, IBA, ADMS, QR, GPS, kiosk, employee-app clock  

This matches Wave 2A and does not require new connector greenfield before a pilot wave.

---

## 6. Setup and support burden (real companies)

Expect **integrator-grade** install, not a dashboard toggle:

- Site + `terminal_sn` ownership registration  
- Sealed connector credentials + rotate/revoke drill  
- Agent host, firewall (no public BioTime inbound), NTP &lt; 30s  
- BioTime API license / version / compat probe (`ingest=false` first)  
- Employee `emp_code` mapping campaign before go-live  
- HR remediation SLA for unknown/duplicate/offline  
- On-call owner + revoke+stop-agent rollback  

Without that ops muscle, enabling ingest creates a support trap.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Wrong employee mapping → dirty authority | Strict map; quarantine; no auto-create |
| Biometric data leak into Wathefni | Sanitizer hard-fail; never request templates |
| Device clock drift | NTP gate; quarantine skew in enablement wave |
| Duplicate / out-of-order punches | source_event_id uniqueness; ambiguous → exception, not money |
| Connector offline silent gap | Health + lag alerts; payroll_exclude incomplete days |
| Premature payroll money | Snapshots only; freeze ban remains |
| Support overload / multi-vendor | Single BioTime pilot; partner later vendors |
| Privacy / location misuse | No GPS/QR product; metadata GPS not authority |
| Consent / workplace monitoring optics | Customer written approval; clear HR policy before pilot |

---

## 8. What must remain frozen (until owner wave)

- `CAPTURE_INGEST=off` outside a named enablement wave  
- No real punches / employee mutations for clocking UX  
- No Payroll money from Attendance  
- No AI  
- No QR / GPS / kiosk / broad employee-app clocking  
- No manager-scope widening for attendance beyond current scoped ops  
- Punch immutability · approve ≠ apply · dual approval · tenant isolation · sealed secrets  
- Sibling freezes (E360, Onboarding, Leave, Shifts, Payroll) untouched  

---

## 9. Qualification plan (if owner authorizes first ingest wave)

**Wave shape:** Controlled BioTime **real-ingest enablement** — not connector rebuild.

1. **Preflight (ingest still off):** full `ATTENDANCE_PILOT_INSTALLATION_CHECKLIST.md`; compat probe PASS; secrets leak-scan PASS; freeze smokes green.  
2. **Policy:** named allowlist (company, site, `terminal_sn`, employee keys or temporary real-subject gate); decide how `AUTHORITY_SYNTHETIC_ONLY` is lifted **only** for that allowlist — never global.  
3. **Staging:** agent → BioTime fixture/lab → map → ingest on staging → projection → exception → approve_day → payroll_excluded vs eligible proof; residual cleanup.  
4. **Production canary:** CAPTURE_INGEST on **only** for allowlisted connector; 24h lag/health SLA; remediation backlog triage; zero secret leaks; sibling freezes + Payroll CAPTURE_INGEST refuse still documented.  
5. **Rollback:** revoke connector + stop agent + ingest off drop-in; prove no money path.  
6. **Exit:** GO freeze addendum for “controlled BioTime ingest” or rollback to ingest-off.

**Still NO-GO inside that wave:** QR/GPS/kiosk, second vendor, payroll money, broad app clocking, AI.

---

## 10. GO / NO-GO

| Question | Verdict |
|---|---|
| Architecture direction (canonical contract + adapters) | **GO** — already chosen and largely built |
| First connector = BioTime + agent | **GO** — correct Kuwait bet |
| Flip `CAPTURE_INGEST` now | **NO-GO** |
| QR / GPS / kiosk / employee-app clock wave | **NO-GO** |
| Hik / BioStar / Anviz / IBA build-now | **NO-GO** (partner/deal-driven later) |
| **First real-ingest wave** | **CONDITIONAL GO** — owner-approved **enablement + single-device pilot qualify** of existing BioTime stack |

### Exact next wave?

**Not a code-gap rebuild.** Research does **not** show a missing core ingest architecture; Wave 2B–2G already shipped BioTime/CSV/agent/pipeline/remediation dark.

If and only if the owner wants live punches: next wave is **Attendance Controlled BioTime Ingest Pilot** (enablement + qualify), using existing checklist/runbook — **after** written customer approval and allowlist. Until then: **no next Attendance ingest wave; keep freeze.**

---

## Sources

- `ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md`  
- `ops/evidence/attendance-final-20260802T131146Z/REPORT.md`  
- `ops/evidence/attendance-wave2a-kuwait-device-architecture-20260802T024341Z/REPORT.md`  
- `ops/evidence/attendance-wave2b-capture-contract-20260802T025055Z/REPORT.md`  
- `ops/evidence/attendance-wave2d-pilot-readiness-20260802T030554Z/REPORT.md`  
- `ops/evidence/attendance-wave2g-dark-20260802T111431Z/REPORT.md`  
- `ops/ATTENDANCE_PILOT_INSTALLATION_CHECKLIST.md`  
- `ops/ATTENDANCE_CONNECTOR_SECRET_RUNBOOK.md`  
- Market: ZenHR↔ZKTeco/BioTimeCloud, Bayzat↔Cams/ZKTeco, KCS IBA Kuwait presence
