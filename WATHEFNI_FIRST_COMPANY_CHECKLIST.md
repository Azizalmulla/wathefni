# Wathefni — First-Company Go-Live Readiness Checklist

> The gate to clear **before onboarding the first real client company** onto the live
> system. Work top-to-bottom; nothing in §0–§6 should be skipped. Pair this with
> `WATHEFNI_V1_OPERATOR_RUNBOOK.md` (how to operate) and the ops runbooks under
> `wathefni-orchestrator/ops/`. Last updated: 2026-06-12.
>
> How to use: check each box only when **verified**, not assumed. Record date + who
> verified next to the section. A box that can't be honestly ticked is a blocker.

---

## 0. Ops safety (must be green before any client data) — VERIFIED 2026-06-12

- [x] Production `/health` returns `200 {"status":"ok"}`.
- [x] Encrypted **offsite backups** pushing daily to Backblaze B2 (verified on-demand push + scheduled 02:30 UTC).
- [x] **Restore drill passed** (pulled latest B2 bundle, decrypted, checksums OK) — prod untouched.
- [x] **Uptime monitor** wired and tested (Healthchecks.io dead-man's switch, 5-min/10-min; pings only when `/health` healthy).
- [ ] **Backup passphrase + B2 credentials stored off-box** in a password manager (owner-confirmed). *← confirm before go-live; without the passphrase, offsite backups can't be restored.*

---

## 1. Security & access

- [ ] All secrets live only in `/root/.openclaw/secrets/` at chmod `600`; none committed to git.
- [ ] No default/shared dashboard token left enabled as a login path once real Owner accounts exist (legacy token-seeding path is for bootstrap only).
- [ ] TLS valid on `https://api.wathefni.ai` (Caddy auto-cert), HTTP→HTTPS redirect works.
- [ ] DNS for `api.wathefni.ai` points at the VPS and is under your control (registrar creds in the password manager).
- [ ] VPS access limited to known keys; root login over password disabled.
- [ ] Off-box password manager holds: VPS access, DNS/registrar, Backblaze B2, backup passphrase, Postmark, Healthchecks.io.
- [ ] RBAC deny-paths spot-checked: a `viewer`/`manager` cannot hit a `*.manage` action; a `manager` sees only their team (manager scoping), not company-wide lists.

---

## 2. Tenant / company provisioning

- [ ] Company created with the correct `company_code` (uppercase, e.g. `ACME`).
- [ ] **Enabled modules** for the company match what was sold (verify via `/dashboard/auth/me` → `enabled_modules`). Disabled modules must not appear in the UI.
- [ ] First **Owner / Super Admin** account created and login confirmed (company code + email + password).
- [ ] Additional users invited with **correct roles** (HR Manager, Team Manager, Viewer, etc.); each accepted and logged in.
- [ ] Team Managers have their **manager scope** assigned so they see only their team.
- [ ] WhatsApp identities linked for any user who acts over WhatsApp (phone set on invite).
- [ ] Tenant isolation re-confirmed: logged in as this company, no data from `WATHEFNI` or any other tenant is visible.

---

## 3. Data setup

- [ ] Employees added or imported; spot-check names, phones, departments, start dates.
- [ ] `employee_key` integrity: editing an employee's phone/email preserves history (no duplicates).
- [ ] Onboarding checklists present for active employees where expected.
- [ ] **Leave policy preset reviewed.** Kuwait private-sector preset ships `legal_reviewed=false`, `enforced=false`. Confirm the displayed policy (annual/sick/weekend/holidays) is acceptable to the client and understood as **observe-only** (it does not block approvals in V1). Have legal review before any future enforcement.
- [ ] Public holidays for the period loaded (so chargeable-day math is sensible).
- [ ] Shifts/attendance baseline configured if those modules are in scope.

---

## 4. Product surfaces (click-through as the client's Owner)

- [ ] Each enabled module loads with no errors: Onboarding, Compliance, Employees / Employee 360, Shifts, Attendance, Leave, Payroll, Analytics.
- [ ] **Employee 360** opens; Quick Slice / Next Actions render; documents (if any) view/download via the Document Hub (no raw storage URLs).
- [ ] **Leave**: file-on-behalf works; balance chips show with the **"not enforced"** banner; left employees excluded from selectors.
- [ ] **Attendance**: history/date-range + CSV export work.
- [ ] **Shifts**: week navigator, cancel/reschedule work.
- [ ] **Payroll**: period picker, generate/preview, export **download** and **detail** work; `payroll.export` restricted to Owner/HR Manager.
- [ ] **Employee lifecycle**: edit, Mark as left (no delete, history kept), Reactivate — all gated by `settings.manage`.
- [ ] Destructive/sensitive actions show a confirmation; error messages are human-readable (no raw keys/jargon).

---

## 5. Communications

- [ ] **WhatsApp** channel live and reaching real employee numbers; inbound employee messages create the expected records.
- [ ] **Postmark** sending domain/signature verified; a real test email (e.g. an invite) delivers and isn't flagged as spam.
- [ ] Outbound delivery flows behave: confirm `employee_messages` write with correct flow/status and `hr_tasks` are created only when expected. (Flows `onboarding/compliance/shift` are mid-soak — watch them through the first weeks.)
- [ ] Out-of-session WhatsApp **templates** remain OFF unless approved template names are configured (`WATHEFNI_OUTBOUND_TEMPLATES`).

---

## 6. Feature-flag state for go-live

Confirm on the running prod process (`tr "\0" "\n" < /proc/$(systemctl show -p MainPID --value wathefni-orchestrator.service)/environ | grep -i WATHEFNI_`):

- [ ] `WATHEFNI_OUTBOUND_LAYER=on`
- [ ] `WATHEFNI_LEAVE_BALANCES=on` (observe-only — does not block)
- [ ] `WATHEFNI_OUTBOUND_TEMPLATES=off` (until approved templates)
- [ ] `WATHEFNI_ONBOARDING_HR_MUTATE`, `WATHEFNI_DOC_UPLOAD`, `WATHEFNI_ORG_HIERARCHY` = intended state (OFF unless deliberately canaried for this client).
- [ ] Any flag turned ON for this client was canaried on one employee first and is revertible by flipping it off.

---

## 7. Go-live cutover & rollback

- [ ] Latest code is **staging-green** and the exact prod `app.py` matches the recorded green hash.
- [ ] A fresh **pre-go-live backup** taken and confirmed pushed offsite.
- [ ] Rollback path rehearsed mentally: `ops/deploy.sh rollback` for bad code; **flag off** for a misbehaving feature; `RESTORE_RUNBOOK.md` for data.
- [ ] First-hour watch plan: app health, edge 200, uptime log `ping=OK`, no error spike in `journalctl -u wathefni-orchestrator.service`.
- [ ] Operator on call knows where the runbook, secrets (password manager), and escalation contacts are.

---

## 8. Known V1 limits to disclose internally

- Single VPS, no automatic failover; recovery from total host loss is a **manual** restore to a new box (needs B2 creds + backup passphrase).
- Uptime check probes the **app port**, not Caddy/TLS specifically (edge `/health` not exposed) — watch the edge in daily checks.
- Leave balances are **observe-only**; no enforcement, no policy/holiday editor UI yet (legal review pending).
- Org-hierarchy admin UI, HR onboarding mutations, and HR document upload exist in code but are **OFF** by default.
- Per-service crash alerts (systemd `OnFailure`) are not wired into the single uptime check by design; add a separate channel if fast crash paging is needed.

---

## 9. Sign-off

| Area | Verified by | Date | Notes |
|---|---|---|---|
| Ops safety (§0) | | | |
| Security & access (§1) | | | |
| Provisioning (§2) | | | |
| Data setup (§3) | | | |
| Product surfaces (§4) | | | |
| Communications (§5) | | | |
| Flags (§6) | | | |
| Cutover/rollback (§7) | | | |

**Go-live approved by:** ______________________  **Date:** ____________
