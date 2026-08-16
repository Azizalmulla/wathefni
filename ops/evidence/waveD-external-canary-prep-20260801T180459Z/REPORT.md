# Wave D — External canary preparation (forwarding-only)

**Stamp:** `20260801T180459Z`  
**Mode:** Preparation only — **nothing enabled**  
**Scope:** One approved external company, forwarding intake only  
**Connectors:** Gmail/M365 remain **dark**; `WATHEFNI_MAILBOX_SYNC=off`  
**Post-hiring:** not started  

Evidence: `ops/evidence/waveD-external-canary-prep-20260801T180459Z/`

---

## GO / NO-GO

| Decision | Result |
|---|---|
| **Prepare** external forwarding canary pack | **GO** |
| **Enable** allowlist / tenant now | **NO-GO** (explicitly deferred) |
| Enable Gmail/M365 sync | **NO-GO** |
| Broader GA | **NO-GO** |
| Post-hiring | **NO-GO** |

**Activation GO** requires: named `<COMPANY_CODE>`, signed privacy acknowledgement, owner admin ready, kill-switch drill scheduled, monitoring daily owner assigned, and explicit operator approve to edit allowlist.

---

## Safest customer profile (recommend)

Pick **one** company that matches most of:

1. Already live on Wathefni pre-hiring (account exists; owners trained)  
2. Low–moderate CV volume (**≤50 CVs/day** week 1; fits **starter** plan)  
3. Single recruitment mailbox already used (Outlook/M365 or Gmail forward capable)  
4. HR owner available daily for Held review (EN and/or AR)  
5. Willing to run **forwarding-only** (no mailbox OAuth)  
6. Not a multi-brand / multi-entity share-mailbox edge case  
7. No regulatory “must delete within 24h” requirement during canary (retention execute still off)  
8. Prefer Kuwait/GCC timezone overlap with Wathefni ops for first week  

**Avoid for first external canary:** agencies blasting high volume, shared inboxes with mixed non-CV mail, customers demanding mailbox sync, or first-time Wathefni logos with no trained owner.

Placeholder in all drafts: `<COMPANY_CODE>` (uppercase, exact DB `companies.company_code`).

---

## Activation plan (when approved — not executed)

### Day −2 to −1 (prep, still no allowlist change)
1. Confirm company row exists; `pre_hiring` entitlement on; owner users exist.  
2. Create **general** intake address (`needs_role`) via Settings or API (`settings.manage`).  
3. Optional: create **one** job alias (`role_bound`) for a single open, stable position.  
4. Set enterprise plan to **`starter`**, soft warn 80%, kill_switch **false**.  
5. Deliver EN/AR checklist + privacy notice; customer configures forward but can point to address early (mail will fail-closed until allowlisted).  
6. Assign Wathefni ops owner for daily report.  
7. Snapshot allowlist drop-ins + health (rollback baseline).

### Day 0 (enable — requires separate GO)
1. Apply exact allowlist: `WATHEFNI,<COMPANY_CODE>` in **all** drop-ins that set `INBOUND_ALLOWED` (see `artifacts/allowlist-change.DRAFT.conf`).  
2. Keep `WATHEFNI_MAILBOX_SYNC=off`.  
3. Reload systemd; restart orchestrator; verify health 200 + env.  
4. Customer sends **1 external test CV**; ops confirms Held item + clean scan.  
5. Kill-switch drill: on → confirm `waiting_budget` → off.  
6. Customer HR admits test candidate to role (or archives) to prove path.

### Days 1–7 (core canary)
- Daily usage / quarantine / failure / backlog report (SQL in monitoring matrix)  
- Soft-warn if approaching starter caps; no hard SMTP reject  
- No connector enablement; no second external tenant  

### Days 8–14 (optional stretch)
- Only if success criteria met through day 7  
- Slight volume increase OK within starter caps  
- Decision: keep / extend / add 2nd company / abort  

---

## Exact tenant allowlist change

See `artifacts/allowlist-change.DRAFT.conf`.

```
WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI,<COMPANY_CODE>
WATHEFNI_MAILBOX_SYNC=off   # unchanged
```

Update every drop-in that currently hardcodes `WATHEFNI` alone (`waveD-phase2-inbound-allowlist.conf` and any duplicate in `waveD-phase3-enterprise.conf`).

---

## Dedicated intake address + optional job alias

| Item | Spec |
|---|---|
| Domain | `inbound.wathefni.ai` |
| General alias | label e.g. `<COMPANY_CODE> canary general`; hold `needs_role` |
| Job alias (optional) | one open `position_code`; hold `role_bound` |
| Create API | `POST /dashboard/prehire/integrations/intake` (requires `pre_hiring` + `settings.manage`) |
| Disable / rotate | customer self-serve; prefer disable over delete |

Do **not** create addresses for other companies. Do **not** enable mailbox connections.

---

## Customer admin permissions

| Role / capability | Required |
|---|---|
| Company **owner** (or equivalent with `settings.manage`) | Create/disable/rotate intake; view setup EN/AR |
| Pre-hiring entitlement | Enabled |
| Held Intake review | Owner/HR with import intake + assign/admit permissions |
| Kill switch / plan | Owner via inbound plan update (or Wathefni platform ops) |
| Platform ops | Wathefni only — monitor alerts, allowlist, global brakes |

Minimum customer staffing: **1 owner admin** + **1 HR reviewer** (can be same person for tiny teams).

---

## Privacy / retention notice

See `checklists/privacy-retention-notice.md`.  
Retention execute remains **off**. Forwarding-only; no mailbox sync. Explicit Held admit.

---

## Monitoring, alerts, daily report

See `runbooks/monitoring-matrix.md`.

- Timers: `wathefni-inbound-intake-worker.timer`, `wathefni-inbound-ops-monitor.timer` (already active)  
- Canary-scoped SQL daily report (usage, waiting_quota/budget, open jobs, dead_letter 24h, Held open, non-clean docs)  
- Soft warn at 80% of **starter** caps  
- Tune expectation: `non_wathefni_*` ops alerts will fire once canary is live — treat as expected or add canary dashboard before enablement  

---

## Emergency kill switch

Tenant: `inbound_enterprise.kill_switch=true` → `waiting_budget` / `tenant_kill_switch`.  
Hard revoke: allowlist back to `WATHEFNI` only.  
Details: `runbooks/support-rollback.md`.

---

## Success / stop criteria

See `runbooks/success-stop-criteria.md`.  
7-day core success bar; 14-day stretch; abort on cross-tenant, sync-on, or systemic dead-letter/backlog.

---

## 7–14 day canary plan (summary)

| Window | Focus |
|---|---|
| D−2…D−1 | Address + alias + starter plan + training; **no allowlist change** |
| D0 | Allowlist enable + test CV + kill drill |
| D1–D3 | Stabilize; daily report; Held coaching |
| D4–D7 | Prove volume + idempotency + no silent loss; decide stretch |
| D8–D14 | Optional; then keep / expand carefully / stop |

---

## Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Drop-in override leaves allowlist at WATHEFNI-only or opens extra codes | High | Edit **all** INBOUND_ALLOWED drop-ins; verify `systemctl show` |
| Non-CV mail floods starter caps | Medium | Customer filter “has attachment”; starter waiting_quota never-reject |
| Ops monitor noise (`non_wathefni_*`) | Low–Med | Canary SQL dashboard; document expected alerts |
| Held backlog if HR unavailable | Medium | Daily owner; stop criteria on backlog |
| Fixture/identity pollution across tenants | Low | Tenant-scoped keys; don’t share emails across proof tenants |
| Accidental mailbox sync enable | High | Keep phase5 conf `MAILBOX_SYNC=off`; verify each restart |
| Retention expectations mismatch | Low | Written notice; execute off |

---

## Rollback plan (order)

1. Tenant kill switch **on**  
2. Disable canary intake addresses  
3. Customer pauses forward rule  
4. Allowlist → `WATHEFNI` only; reload + restart  
5. Verify health, sync off, no new canary submissions  
6. RCA if abort criteria met  

---

## Deliverables in this pack

| Path | Content |
|---|---|
| `artifacts/allowlist-change.DRAFT.conf` | Exact env change (not applied) |
| `artifacts/prod-posture-readonly.txt` | Live posture snapshot |
| `checklists/forwarding-setup-EN-AR.md` | Customer checklist |
| `checklists/privacy-retention-notice.md` | Privacy notice |
| `runbooks/monitoring-matrix.md` | Alerts + daily SQL |
| `runbooks/support-rollback.md` | Kill / revoke |
| `runbooks/success-stop-criteria.md` | Go/stop bars |
| `assess/go-no-go.json` | Machine-readable decision |

---

## What was **not** done

- No allowlist edit  
- No intake address created for an external company  
- No mailbox sync / connector enablement  
- No post-hiring  
- No production code deploy  
