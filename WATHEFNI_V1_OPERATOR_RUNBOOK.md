# Wathefni — V1 Operator Runbook

> For the person **operating the live Wathefni service** day-to-day (not building it).
> If you are joining to write code, read `WATHEFNI_HANDOFF.md` first.
> Deep ops procedures live in `wathefni-orchestrator/ops/DEPLOY_RUNBOOK.md` and
> `wathefni-orchestrator/ops/RESTORE_RUNBOOK.md`; this runbook is the operator's index to them.
> Last updated: 2026-06-12.

---

## 0. The 60-second mental model

- **What it is:** a single FastAPI backend + a React dashboard, one PostgreSQL DB, on **one VPS**, fronted by Caddy (TLS). Employees/candidates talk to it over WhatsApp; HR uses the web dashboard.
- **Where it lives:** VPS `root@76.13.63.68`, public edge `https://api.wathefni.ai`, dashboard at `https://api.wathefni.ai/dashboard`.
- **Tenancy:** everything is scoped by `company_code` (e.g. `WATHEFNI`). One install can host multiple companies; data never crosses tenants.
- **Safety posture:** sensitive/mutating features are dark-launched behind flags (default OFF), enabled via a one-employee canary, and revertible by flipping the flag off.
- **What protects you:** daily encrypted offsite backups to Backblaze B2 (restore-drilled), and a Healthchecks.io uptime monitor that pages you if the site stops responding.

---

## 1. Access & accounts

| Thing | Where | Notes |
|---|---|---|
| Public dashboard | `https://api.wathefni.ai/dashboard` | What clients/HR use. |
| Backend API | `https://api.wathefni.ai/dashboard/...` | JSON only; never serves the SPA shell. |
| VPS (root) | `ssh root@76.13.63.68` | Override host with `WATHEFNI_VPS_HOST`. |
| Prod app | `/opt/wathefni/orchestrator`, port `:8010`, `wathefni-orchestrator.service` | |
| Staging app | `/opt/wathefni/staging/orchestrator`, port `:8011`, `wathefni-orchestrator-staging.service` | SSH-tunnel only, no public domain. |
| Secrets | `/root/.openclaw/secrets/*` (chmod 600) | DB env, backup passphrase, B2 creds, Healthchecks URL. **Never commit.** |

### Dashboard login
Operators/HR log in with **company code + email + password** at `/dashboard/auth/login`. Sessions are bearer tokens. There is no public self-signup — accounts are created by invite.

### Roles (RBAC) — what each can do
Permissions are enforced on the backend (`require_entitlement`) and mirrored on the frontend (`can()`). A user only ever sees data their **role** AND their **manager scope** allow.

| Role (label) | Internal key | In short |
|---|---|---|
| Owner / Super Admin | `owner` | Everything, incl. **manage users** and **settings**. The only role that can invite/manage other users. |
| HR Manager | `hr_manager` | Full HR + payroll incl. `payroll.export`, settings — but **cannot** manage users. |
| Team Manager | `manager` | Post-hire ops for **their own team only**: approve leave, fix attendance, approve shifts/timesheets. No company-wide lists, no settings/users, no payroll export. |
| Recruiter / HR Officer | `recruiter` | Pre-hire only (candidates, interviews, assessments, report export). |
| Hiring Manager / Dept Manager | `hiring_manager` | Pre-hire read + interviews + read-only post-hire for their scope. |
| Viewer | `viewer` | Read-only everywhere it's granted. |

> Rule of thumb: reads need `*.read`, mutations need `*.manage`, money export needs `payroll.export`. **Module entitlement** (`company_has_module`) gates everything on top of role — a company only sees modules it's enabled for.

---

## 2. Daily / weekly operational checks

**Daily (≈2 min):**
```bash
# App + edge healthy?
ssh root@76.13.63.68 'systemctl is-active wathefni-orchestrator.service caddy; \
  curl -s -o /dev/null -w "app_health=%{http_code}\n" http://127.0.0.1:8010/health'
curl -s -o /dev/null -w "edge=%{http_code}\n" https://api.wathefni.ai/dashboard

# Uptime monitor still pinging green? (should show recent "ping=OK")
ssh root@76.13.63.68 'tail -n 5 /var/log/wathefni-uptime.log'

# Last offsite backup pushed? (should be today, ~02:30 UTC)
ssh root@76.13.63.68 'systemctl list-timers wathefni-backup.timer --no-pager | head -2; \
  tail -n 5 /var/log/wathefni-backup.log 2>/dev/null'
```
Also glance at the **Healthchecks.io dashboard** — the check should be green.

**Weekly (≈10 min):**
- Confirm a **weekly** backup bundle exists locally and offsite (B2).
- Skim outbound delivery health while the soak is active (see §6): `employee_messages` by flow/status, and open `hr_tasks`.
- Confirm disk isn't filling: `ssh root@76.13.63.68 'df -h / ; du -sh /opt/wathefni/backups'`.

**Monthly:**
- Run a **restore drill** (see `RESTORE_RUNBOOK.md`) — pull the latest offsite bundle, decrypt, verify checksums. Never restore onto prod.
- Verify the backup passphrase + B2 credentials are still in the off-box password manager.

---

## 3. Common operator tasks

### Add a dashboard user (invite)
Only an **Owner** can. In the dashboard: Team → Invite, choose role. The invitee gets a link, sets a password (≥8 chars), and is active. (API: `POST /dashboard/team/invites`, accept via `POST /dashboard/team/invites/accept`.) If the user will also act over WhatsApp, set their phone on the invite so the WhatsApp identity links automatically.

### Change a user's role / deactivate
Owner → Team → edit role or set status inactive. Deactivated users are denied at login; their historical actions are preserved.

### Add / import employees
Dashboard → Employees → **Add employee** (single) or **Import** (bulk). Employee records are keyed by an immutable `employee_key`; editing a phone/email keeps history intact. To offboard, use **Mark as left** (deactivates; never deletes), and **Reactivate** to restore.

### Enable a module or feature flag (sensitive — canary first)
Flags are systemd env, set via drop-ins:
```bash
ssh root@76.13.63.68
mkdir -p /etc/systemd/system/wathefni-orchestrator.service.d
cat > /etc/systemd/system/wathefni-orchestrator.service.d/<feature>.conf <<'EOF'
[Service]
Environment=WATHEFNI_<FLAG>=on
EOF
systemctl daemon-reload && systemctl restart wathefni-orchestrator.service
```
Then verify it's live (§7), run a **one-employee canary**, confirm, and decide keep/revert. To revert: remove the drop-in (or set `=off`), `daemon-reload`, restart.

### Deploy a change
Never edit code on the VPS. From the operator machine:
```bash
cd wathefni-orchestrator
ops/deploy.sh staging      # builds dashboard, deploys to :8011, runs full smoke suite, records staging-green
ops/deploy.sh production   # refuses unless that exact app.py passed on staging
ops/deploy.sh rollback     # restore the most recent pre-deploy prod snapshot
```
Full details and the pre/post checks are in `ops/DEPLOY_RUNBOOK.md`.

---

## 4. Monitoring & alerting (what an alert means)

- **Uptime — Healthchecks.io dead-man's switch.** Every 5 min, `wathefni-uptime.timer` probes `http://127.0.0.1:8010/health` and pings Healthchecks **only** when it returns `200 {"status":"ok"}`. If `/health` fails or the box is down, no ping is sent and Healthchecks alerts after its **10-minute grace** (check period is 5 min).
  - **You get an alert ⇒** the site has been unable to confirm health for ~15 min. Go straight to §5 incident response.
  - Ping URL is a secret in `/root/.openclaw/secrets/healthcheck.env` (chmod 600), never in git.
  - Inspect: `tail -n 20 /var/log/wathefni-uptime.log` (`ping=OK` each run).
  - **Test without touching prod:**
    ```bash
    ssh root@76.13.63.68 'WATHEFNI_HEALTH_URL=http://127.0.0.1:9/health /usr/local/bin/wathefni-healthcheck-ping; tail -1 /var/log/wathefni-uptime.log'
    ssh root@76.13.63.68 '/usr/local/bin/wathefni-healthcheck-ping'   # re-ping to leave it green
    ```
  - **Silence (planned maintenance):** `systemctl disable --now wathefni-uptime.timer` AND pause the check in the Healthchecks UI, so the silence doesn't alert. Re-enable both afterward.

> Known gap (V1, accepted): the probe checks the **app port**, not Caddy/TLS specifically (the edge doesn't expose `/health`). A Caddy/TLS-only failure with a healthy app port won't trip this. Watch the edge manually in the daily check.

---

## 5. Incident response

**First, triage what's actually down:**
```bash
ssh root@76.13.63.68 'systemctl is-active wathefni-orchestrator.service caddy postgresql; \
  curl -s -o /dev/null -w "app=%{http_code}\n" http://127.0.0.1:8010/health'
curl -s -o /dev/null -w "edge=%{http_code}\n" https://api.wathefni.ai/dashboard
```

| Symptom | Likely cause | Action |
|---|---|---|
| `app=000`/not 200, service inactive | App crashed | `journalctl -u wathefni-orchestrator.service -n 100`; `systemctl restart wathefni-orchestrator.service`; if it crash-loops on a recent deploy → **rollback**. |
| `app=200` but `edge` fails | Caddy/TLS | `systemctl status caddy`; `journalctl -u caddy -n 100`; `systemctl restart caddy`; check cert/DNS. |
| DB errors in logs | Postgres down/full | `systemctl status postgresql`; check `df -h`; restart Postgres; if data loss suspected → **restore** (`RESTORE_RUNBOOK.md`). |
| Bad deploy (5xx, dashboard blank) | Regression | `cd wathefni-orchestrator && ops/deploy.sh rollback`; confirm `prod_health=200`. |
| A sensitive feature misbehaves | Flag rollout | Flip the feature flag **off** (§3) and restart — the safe revert path. |
| Whole VPS unreachable | Host/provider | Check the VPS provider console; once back, the timer auto-resumes and Healthchecks goes green. Worst case: restore to a fresh box (manual; needs B2 creds + backup passphrase from the password manager). |

**Always after resolving:** confirm `app_health=200`, `edge` 200, and the uptime log resumes `ping=OK` (Healthchecks turns green).

---

## 6. Backups, restore & current soak

- **Backups:** daily at ~02:30 UTC (`wathefni-backup.timer`) — DB dump + files + encrypted secrets, AES256-encrypted, pushed **offsite to Backblaze B2** (`wathefni-offsite:…/offsite`). Retention 7 daily + 4 weekly, local and offsite. Pre-deploy snapshots under `/opt/wathefni/backups/predeploy-*`.
- **Restore:** see `ops/RESTORE_RUNBOOK.md`. **Never restore onto prod.** Offsite bundles **cannot be decrypted without the backup passphrase** — it must live in the off-box password manager along with the B2 account credentials. This is the single point of recovery; verify monthly.
- **Restore drill verified:** 2026-06-12 (pulled latest B2 bundle, decrypted, checksums OK).
- **Active soak (monitor):** outbound delivery flows `onboarding`, `compliance`, `shift` were recently expanded. Watch `employee_messages` (by flow/status) and open `hr_tasks` until stable. Outbound WhatsApp **templates** flow remains OFF until approved template names exist.

---

## 7. Feature flags — verify & current intent

**See the live values on the running prod process:**
```bash
ssh root@76.13.63.68 'tr "\0" "\n" < /proc/$(systemctl show -p MainPID --value wathefni-orchestrator.service)/environ | grep -i WATHEFNI_'
```

| Flag | Intended V1 state | Meaning |
|---|---|---|
| `WATHEFNI_OUTBOUND_LAYER` | on | Shared outbound delivery layer. |
| `WATHEFNI_OUTBOUND_FLOWS` | leave_decision,onboarding,compliance,shift | Flows routed through it (mid-soak). |
| `WATHEFNI_OUTBOUND_TEMPLATES` | off | Out-of-session WhatsApp templates — off until approved. |
| `WATHEFNI_LEAVE_BALANCES` | on (observe-only) | Shows balances; **never blocks** approvals. |
| `WATHEFNI_ONBOARDING_HR_MUTATE` | off | HR onboarding mutations from dashboard. |
| `WATHEFNI_DOC_UPLOAD` | off | HR document upload from dashboard. |
| `WATHEFNI_ORG_HIERARCHY` | off | Org hierarchy / manager-scope admin features. |

> Flipping any of these is a §3 "sensitive" change: drop-in → restart → verify → canary → keep/revert.

---

## 8. Guardrails (do NOT violate)

- **Tenant scoping is mandatory.** Never run a query or expose a list that isn't scoped by `company_code`.
- **Observe-only stays observe-only.** Leave balances must never block an approval in V1.
- **Dark-launch + canary** every sensitive/mutating change; default OFF in prod; revert = flag off.
- **Strict staging→prod**: local build → staging smoke green → recorded green hash → prod deploy (gated) → public-route guard → health check. No editing code on the VPS.
- **No raw sensitive data in logs.** Audit via the admin audit trail (metadata only).
- **Secrets never enter git.** They live only in `/root/.openclaw/secrets/` (chmod 600) and the off-box password manager.

---

## 9. Escalation / key facts

- **Hosts:** VPS `root@76.13.63.68`; edge `https://api.wathefni.ai`; DNS for `api.wathefni.ai` must point at the VPS; TLS via Caddy (auto).
- **Email:** Postmark (live outbound provider). Verify the sending domain/signature before go-live.
- **Off-box secrets (password manager):** backup passphrase, Backblaze B2 credentials, VPS access, DNS/registrar, Postmark, Healthchecks.io account.
- **Reference docs:** `WATHEFNI_HANDOFF.md` (engineering), `ops/DEPLOY_RUNBOOK.md` (deploy), `ops/RESTORE_RUNBOOK.md` (restore), and the first-company checklist `WATHEFNI_FIRST_COMPANY_CHECKLIST.md`.
