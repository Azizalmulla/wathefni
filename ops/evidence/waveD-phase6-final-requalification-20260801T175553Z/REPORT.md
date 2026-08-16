# Wave D Phase 6 — Final requalification (post D6A + D6B)

**Stamp:** `20260801T175553Z`  
**Mode:** Production requalification only — **no code change**, **no external-tenant enablement**, **no post-hiring**.  
**Host:** `root@76.13.63.68`  
**Code under test:** current production after D6A held-materialization + D6B cv_extraction repair  

Local evidence: `ops/evidence/waveD-phase6-final-requalification-20260801T175553Z/`  
Remote evidence: `/opt/wathefni/production-evidence/waveD-phase6-final-requal/20260801T175553Z/`

---

## Final recommendation: **controlled external canary (forwarding-only)**

| Decision | Result |
|---|---|
| **Overall Wave D inbound** | **controlled external canary** (forwarding product) |
| WATHEFNI forwarding (current live) | **GO** — remain enabled |
| External-tenant enablement (this run) | **Not enabled** (operator decision deferred) |
| Premium Gmail/M365 connector GA | **NO-GO** (remain dark; sync off) |
| Broader multi-tenant GA | **NO-GO** until controlled external canary succeeds |
| Post-hiring | **not started** |

Previous D6 GA (`20260801T160950Z`) was **limited canary / external NO-GO** solely because `durable_to_held_materialization_synthetic` **FAIL**. That blocker is now **PASS** after D6A+D6B. Extraction promotion (previously deferred) is also **PASS**.

---

## Previously failed gates — re-run results

| Gate | Prior | Requal | Evidence |
|---|---|---|---|
| Durable → Held materialization (D6A) | **FAIL** | **PASS** | `verify/prod-d6a-requal.json` (rich + conflict + opaque) |
| CV extraction promotion PDF/DOCX (D6B) | deferred / broken | **PASS** | `verify/prod-d6b-requal.json` |

D6A highlights: short/accepted Held, conflict warned Held, opaque Held+warning, Message-ID idempotent.  
D6B highlights: rich PDF promotes email; rich DOCX full success; conflict uses `held_identity_review_scan_clean`; opaque soft-completes; no indefinite pending; no duplicates.

---

## Final capability matrix

| Capability | Result | Notes |
|---|---|---|
| Forwarding intake create/list/disable | **PASS** | Live requal |
| General + job-specific aliases | **PASS** | `needs_role` + `role_bound` |
| Held Intake review + admit path | **PASS** | Queue visible; assign/admit/bulk APIs present; prior D6 GA admit/bulk PASS unchanged |
| PDF extraction + field promotion | **PASS** | Live D6B |
| DOCX extraction + same path | **PASS** | Live D6B full success |
| Identity / conflict / opaque handling | **PASS** | Live D6A + D6B |
| Duplicates / idempotency | **PASS** | Forwarding Message-ID + extraction re-drain=0 |
| Quotas + soft warn | **PASS** | Live posture + prior D6 GA PASS |
| Burst overrides | **PASS** | Override set/clear live; prior GA PASS |
| Kill switch | **PASS** | Live `waiting_budget` / `tenant_kill_switch` |
| Outage / replay | **PASS** | Prior D6 GA dead_letter→pending PASS; D6B soft-fail bounds extraction |
| Retention | **PASS** | Execute **off**; dry-run readiness |
| Gmail/M365 connector posture | **PASS (dark)** | Sync **off**; prior D5/D6 connector deep PASS; not re-enabled |
| Tenant isolation | **PASS** | WATHEFNI allowlist; ACMECORP / unknown recipient fail-closed |
| Environment isolation | **PASS** | Production marker + Postmark env pin |
| EN/AR desktop/mobile | **PASS** | Prior D4/D5/D6 UI evidence; no UI change in D6A/D6B |
| Cleanup + rollback posture | **PASS** | Proof intakes disabled; D3–D6B `ROLLBACK.sh` present; timer restored |
| Health | **PASS** | orch=200, dash=200 |

Live requal scoreboard: **38 PASS / 0 FAIL** (`verify/prod-d6-requal-matrix.json`).

Prior D6 GA deep cases carried forward under unchanged posture (admit/bulk, connector OAuth deep path, concurrency, ClamAV replay): see `assess/final-matrix.json` → `prior_ga_carryforward`.

---

## Production SHAs (unchanged this run)

| Artifact | SHA-256 |
|---|---|
| `orchestrator/app.py` | `27c7e2f0d8fe110b2683a0173b29122c5293411a64a71fcb865cdab8d079e790` |
| `orchestrator/inbound_cv_authority.py` | `8cf1759371a2a3d4f1f42125e1ba960ae34db23f6c173f657aa1532cd95a4fab` |

---

## Remaining blockers by severity

### Critical
*None.*

### Medium
*None for WATHEFNI forwarding.*  
*(Former MEDIUM durable→Held FAIL is closed.)*

### Low
1. **M365 dedicated mailbox OAuth app unset** — expected while premium connectors stay dark.  
2. **Inbound alert pack depth** — ops timers + usage API exist; multi-tenant `dead_letter` / `waiting_budget` alert pack still thin.  
3. **Synthetic residue hygiene** — requal needed one sterilize pass of leftover provisional names/keys before D6B retry (fixture pollution, not product defect).  
4. **D6 GA `dead_letter` leftover** (`90887c19-…` / `d6ga-08343d30-kill`) — classified synthetic; preserved untouched.

---

## Operational readiness

| Area | Status |
|---|---|
| Live canary posture | `WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI`, `MAILBOX_SYNC=off`, retention execute off |
| Worker / ops timers | Active after requal |
| Continuous intake | Postmark default remains the sole continuous active address after cleanup |
| Support brakes | Kill switch, disable address, pause/disconnect connectors, rollback scripts |
| Monitoring | Intake worker + ops-monitor timers |
| Ready to operate WATHEFNI forwarding | **Yes** |
| Ready for controlled external forwarding canary | **Yes (when operator enables allowlist)** |
| Ready for connector GA / broader GA | **No** |

---

## Enablement posture (unchanged during requal)

```
WATHEFNI_INBOUND_EMAIL=on
WATHEFNI_INBOUND_ALLOWED_COMPANIES=WATHEFNI
WATHEFNI_MAILBOX_SYNC=off
WATHEFNI_INTAKE_RETENTION_EXECUTE=off
WATHEFNI_POSTMARK_INBOUND_ENV=production
WATHEFNI_POSTMARK_INBOUND_ENV_PIN=production
```

External tenants were **not** enabled. Post-hiring was **not** started. No application code was changed.

---

## Cleanup proof

`cleanup/cleanup-final.json` + matrix cleanup block:

- `wave_d6_requal*` intakes disabled  
- Active continuous WATHEFNI intakes restored to pre-existing Postmark default only  
- Kill switch off; mailbox sync off  
- Health final: orch=200, dash=200

---

## Evidence path

Local: `ops/evidence/waveD-phase6-final-requalification-20260801T175553Z/`  
Remote: `/opt/wathefni/production-evidence/waveD-phase6-final-requal/20260801T175553Z/`

Key artifacts:
- `verify/prod-d6a-requal.json` — durable→Held re-gate  
- `verify/prod-d6b-requal.json` — PDF/DOCX extraction re-gate  
- `verify/prod-d6-requal-matrix.json` — live capability matrix (38/0)  
- `assess/final-matrix.json` — dimension map + recommendation  
- `before/prior-d6-ga-matrix.json` — prior GA baseline (41/1)
