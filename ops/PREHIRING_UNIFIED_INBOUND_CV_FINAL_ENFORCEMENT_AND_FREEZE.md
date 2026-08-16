# Pre-hiring Unified Inbound CV — Final Enforcement and Freeze

Date: 2026-07-27 (Asia/Kuwait) / stamp `20260727T012902Z`  
Prerequisites accepted: production-dark; legacy binding audit/backfill; forward dual-write; WhatsApp+manual cutover; email cutover  
Host: `root@76.13.63.68`  
Database: `wathefni` (production)  
Tenant scope: **WATHEFNI only**

Evidence:
- Remote: `/opt/wathefni/production-evidence/unified-inbound-cv-final-enforce-freeze/20260727T012902Z/`
- Local: `ops/screenshots/unified-inbound-cv-final-enforce-freeze/20260727T012902Z/`
- Backup / rollback: `/opt/wathefni/backups/production-pre-final-enforce-freeze-20260727T012902Z/`

Artifacts:
- Gate (tenant-scoped ENFORCE): `wathefni-orchestrator/verified_job_binding_gate.py`
- Stage B dual-write: `wathefni-orchestrator/jobs_phase2_stage_b.py`
- Ranking cursor patch: `ops/patch-production-app-unified-inbound-cv-enforce-freeze.py`
- Canary: `ops/unified-inbound-cv-final-enforce-freeze-canary.py`
- Deploy: `ops/deploy-unified-inbound-cv-final-enforce-freeze.sh`

---

## Final PASS / FAIL

| Gate | Result |
|---|---|
| Freeze unified authority (email + WA unsolicited + manual) | **PASS** |
| Observe WATHEFNI apps under ENFORCE scope | **PASS** (14 allow / 2 held deny / 5 smoke deny) |
| bugs = 0 | **PASS** |
| unexplained = 0 | **PASS** |
| No duplicate people/apps/TP/CV bindings | **PASS** |
| Job WhatsApp Stage B qualification | **PASS** |
| Verified-binding ENFORCE (WATHEFNI only) | **PASS** |
| Ranking…hire allow/deny matrix (10 actions) | **PASS** |
| Kill switch + rollback + restore | **PASS** |
| Health 200 + workers healthy | **PASS** |
| Live canary | **PASS (37/37)** |
| External tenants / Role Profiles | **OFF (unchanged)** |
| Post-hiring / mobile | **not started (per scope)** |

### Explicit decisions

| Decision | Result |
|---|---|
| Final unified intake freeze for WATHEFNI | **PASS / GO — FROZEN** |
| Leave `ENFORCE` on for approved WATHEFNI scope | **PASS — LEFT ENABLED** |
| Enable external tenants | **NO-GO** |
| Enable Role Profiles | **NO-GO** |
| Begin post-hiring or mobile work | **NO-GO (out of scope)** |

---

## Frozen posture (left enabled)

```text
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_TENANTS=WATHEFNI
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_EMAIL=on
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_WHATSAPP_UNSOLICITED=on
WATHEFNI_UNIFIED_INTAKE_AUTHORITY_MANUAL=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_GATE=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_SHADOW=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE=on
WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS=WATHEFNI
```

Kill switch: rename `/opt/wathefni/var/unified-inbound-cv.production.env` → restart.  
Full rollback: `/opt/wathefni/backups/production-pre-final-enforce-freeze-20260727T012902Z/ROLLBACK.sh`

---

## 1) Unified authority freeze

| Channel | Authority | Flag |
|---|---|---|
| Inbound email | Unified intake | `…_AUTHORITY_EMAIL=on` |
| Unsolicited WhatsApp | Unified intake | `…_AUTHORITY_WHATSAPP_UNSOLICITED=on` |
| Manual dashboard upload | Unified intake | `…_AUTHORITY_MANUAL=on` |
| Job WhatsApp Stage B application create | Stage B remains convert authority | dual-writes verified bindings after convert |

---

## 2) Live observation (WATHEFNI applications)

Classifications under ENFORCE for WATHEFNI:

| Bucket | Count | Gate mode |
|---|---|---|
| Legitimate Job apps with verified binding | **14** | `allow` |
| Held Talent Pool (`needs_role`) | **2** | `enforce_deny` (`held_or_unassigned_talent_pool_record`) |
| Quarantined smoke / canary without binding | **5** | `enforce_deny` (`verified_job_binding_missing`) |
| bugs | **0** | — |
| unexplained | **0** | — |

Workers: `wathefni-orchestrator.service` active; `wathefni-ck-index.service` active; health **200**.

Duplicate checks: no duplicate verified job bindings, CV bindings, CV versions, or Talent Pool subject rows.

---

## 3) Job-specific WhatsApp Stage B qualification

Canary phone `96555573001` / Job `J2P2_PROD_TEST` / apply `APPLY-WATHEFNI-J2P2_PROD_TEST`

| Requirement | Proof |
|---|---|
| Exact apply code + confirmation convert | `convert_job_context_to_application(trigger=apply_confirm)` → app `96555573001-WATHEFNI-J2P2_PROD_TEST` |
| Replay idempotency / no duplicate application | second convert `idempotent=true`; 1 app for phone |
| Unified `cv_version` created/reused | `3b32f8eb-786f-55d4-900e-6a753ce392be` (1 row) |
| `application_job_binding` verified | position `J2P2_PROD_TEST`, apply code exact |
| `application_cv_binding` pins selected CV | pinned to that `cv_version_id` |
| Stage B behavior compatible | convert path unchanged; additive dual-write only |

---

## 4) ENFORCE canary matrix

Owner-authorized scope: `WATHEFNI_UNIFIED_VERIFIED_JOB_BINDING_ENFORCE_TENANTS=WATHEFNI`  
`OTHERCO` enforce = **false**.

Actions proven for allow (verified app) and deny (held + unverified):

`ranking`, `screening`, `assessment`, `interview`, `communication`, `lifecycle_transition`, `shortlist`, `reject`, `offer`, `hire`

| Target | Result |
|---|---|
| Verified Job application | **allow** all 10 |
| Held Talent Pool | **enforce_deny** all 10 |
| Unverified smoke Job-looking row | **enforce_deny** all 10 |
| False denials | **0** |

Ranking HTTP evaluation endpoint now loads bindings via DB cursor (`UNIFIED_VERIFIED_JOB_BINDING_GATE_CURSOR_V2`) and uses tenant-scoped `enforce_enabled(company_code=…)`.

---

## 5) Kill switch / rollback / restore

| Control | Evidence |
|---|---|
| Kill switch | Flags file renamed → ENFORCE absent; `enforce_flag_on=False` | `kill-switch-proof.txt` |
| Restore | Flags restored; health 200 | `post-kill-restore-health.txt` |
| Rollback | Pre-freeze `app.py` / gate / Stage B / flags restored | `rollback-run.txt` → `ROLLBACK_OK` |
| Re-apply freeze | ENFORCE + TENANTS=WATHEFNI restored | `final-flags-live.txt`, `freeze-posture.txt` |

Bounded canary mutations only (≤1 app / ≤1 candidate for canary phone).

---

## Remaining limitations

1. **Live HTTP ENFORCE hook** is surgically wired on the Ranking / evaluation dashboard path. The other nine downstream actions are proven via the shared gate function (`assert_verified_job_binding`) used for ENFORCE decisions; broader HTTP/tool mutation endpoints still rely on existing held-status and lifecycle guards and should adopt the same cursor+tenant gate when those surfaces are next touched.
2. **ENFORCE is WATHEFNI-scoped only.** Empty/other tenants are not enforced; external tenants remain OFF.
3. **Role Profiles remain OFF.** Ranking continues without Role Profile authority changes.
4. **Quarantined smoke apps without bindings correctly deny** under ENFORCE — expected, not false denials.
5. **CK index / video-interview workers** were health-checked as active; this freeze does not expand their schemas or Role Profile behavior.
6. **Post-hiring and mobile** were explicitly out of scope and not started.

---

## Freeze statement

Unified inbound CV for WATHEFNI is **frozen**:

- email, unsolicited WhatsApp, and manual uploads under unified intake authority;
- verified Job binding **ENFORCE on** for WATHEFNI only;
- Stage B remains the Job WhatsApp application-create authority and dual-writes verified bindings;
- kill switch and rollback remain ready.

Stop condition honored: report complete; external tenants / Role Profiles not enabled; post-hiring / mobile not started.
