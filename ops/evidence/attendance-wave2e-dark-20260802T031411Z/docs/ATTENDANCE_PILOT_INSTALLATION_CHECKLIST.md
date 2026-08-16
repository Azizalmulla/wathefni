# Attendance Real-Device Pilot Installation Checklist (Wave 2D)

**Purpose:** Gate the first **allowlisted** customer BioTime site before any live punch ingest.  
**Hard bans until GO:** no real punch ingest, no QR/GPS/kiosk UI, frozen modules unchanged.

Use one checklist per customer / site / device. All boxes must be checked before requesting pilot GO.

## A. Customer / site registration

- [ ] Customer `company_code` registered in Wathefni tenant table
- [ ] Site registered under that company (`timezone=Asia/Kuwait` unless documented exception)
- [ ] Device `terminal_sn` registered and ownership verified for **this** tenant only
- [ ] Wrong-tenant registration attempt tested fail-closed in staging for this customer pattern
- [ ] Connector registration completed; credentials sealed (EnvironmentFile mode 600 / vault)
- [ ] Connector activation recorded with actor phone + audit

## B. Network / firewall

- [ ] On-prem agent host can reach BioTime middleware HTTPS/HTTP on the agreed port only
- [ ] BioTime does **not** need inbound exposure to the public internet for pull mode
- [ ] Outbound from agent to Wathefni ingest endpoint allowlisted (TLS)
- [ ] DNS / NTP reachable; clock skew < 30s vs Kuwait time authority
- [ ] Firewall rules documented (source, dest, port, direction)

## C. BioTime version and fields

- [ ] BioTime version recorded: _____________
- [ ] Read-only compatibility probe PASS (`attendance_capture_compat.run_readonly_compat`) — **ingest=false**
- [ ] Required transaction fields present in sample: `id`, `emp_code`, `punch_time`, `punch_state`
- [ ] Optional fields reviewed: `verify_type`, `terminal_sn`, `terminal_alias`, `work_code`
- [ ] No biometric templates/images in API sample (privacy hard-fail = 0)
- [ ] Timezone of punch_time confirmed (naive → Asia/Kuwait policy agreed)

## D. Security

- [ ] Secrets never on argv / deploy logs / evidence (leak scan PASS)
- [ ] Rotate + revoke drill completed in staging for this connector pattern
- [ ] Operator knows rotate/revoke runbook path: `ops/ATTENDANCE_CONNECTOR_SECRET_RUNBOOK.md`
- [ ] Evidence pack excludes `*.env` and raw secret files

## E. Exception operations

- [ ] HR remediation queue reachable for company
- [ ] Unknown employee/device mapping approve → replay path verified in staging
- [ ] Missing check-in/out and ambiguous order stay `payroll_excluded` until resolved
- [ ] Duplicate/conflict exceptions enqueue without double-writing authority
- [ ] Connector offline / lag alerts visible on health dashboard contract
- [ ] Manager scope / self-action / cross-tenant denials verified

## F. Authority path

- [ ] Accepted punches still flow Wave 1 authority (`ingest_punch` → projection → payroll snapshot)
- [ ] `SYNTHETIC_ONLY` / import flags reviewed for pilot scope (real ingest only if explicitly allowlisted in a later wave)
- [ ] Employees 360 freeze regression green
- [ ] Onboarding freeze regression green

## G. Pilot allowlist (one device)

- [ ] Single site + single `terminal_sn` named: _____________
- [ ] Customer written approval on file
- [ ] Rollback: revoke connector + stop agent unit
- [ ] On-call owner: _____________
- [ ] Success criteria (24h): lag < warn threshold, zero secret leaks, remediation backlog triage SLA agreed

## Sign-off

| Role | Name | Date | Signature |
|---|---|---|---|
| Customer IT | | | |
| Wathefni ops | | | |
| HR ops | | | |

**Verdict until all boxes checked:** NO-GO for real-device pilot.
