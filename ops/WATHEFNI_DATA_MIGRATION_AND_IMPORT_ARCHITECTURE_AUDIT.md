# Wathefni Data Migration & Import Architecture Audit

**Mode:** research + implementation truth only · **no code · no deploy · no real customer data**  
**Date:** 2026-08-04  
**Product rule:** Imported data must never silently become approved or authoritative.

Constrained by freezes: Employees 360 · Onboarding · Attendance · Leave · Shifts · Payroll · Compliance · Analytics · Action Inbox · Platform Assistant · Module-Aware Shell · Setup Console Wave A.

---

## Verdict (one sentence)

Wathefni has **several honest, module-scoped importers** (CV bulk intake, employee roster CSV, Wave 4 org migration, flag-gated attendance punches, payroll external mirror) — but **no Migration Center**, **no millions-of-CVs path**, and **no complete pre-/post-hire historical migration**. Normal small CSV imports are **conditionally production-ready**; enterprise migration is **not**.

| Question | Answer |
|---|---|
| Are normal CSV imports production-ready? | **Partial YES** for roster / org / attendance (flag) / payroll mirror — with hard row/size caps |
| Are millions of CVs possible today? | **NO** |
| Need a first-class Migration Center? | **YES long-term**; **NO as Wave 1** — start with a Migration Foundation spine |
| First migration wave GO/NO-GO? | **GO for research-approved Wave 1 Foundation only** (staging → WATHEFNI synthetic) — **NO-GO** for real customer data |

---

## 1. Current implementation truth

### 1.1 What already exists (real product surfaces)

| Surface | Domain | Limits | Authority posture |
|---|---|---|---|
| Pre-hire **Import Center** (bulk CV + ZIP + optional CSV/XLSX metadata) | Candidates / CVs | **300 files · 250 MB** total/request | Held intake by default; auto-admit fails closed |
| Employee roster CSV/XLSX | Employees | **1000 rows · 5 MB** | Creates hub employees; never overwrites; optional onboarding seed (SEED frozen off) |
| Wave 4 org **migration batches** | Dept/branch/team/position assignments | **500 rows**/batch (policy) | Dry-run / commit / rollback; ambiguous → `needs_review`; **never auto-merge** |
| Attendance Import V1 | Punch history | **20 000 punches · 8 MB**; flag `WATHEFNI_ATTENDANCE_IMPORT` | Preview → commit → reverse; skips payroll-locked days; ≠ CAPTURE_INGEST |
| Payroll external results import | Payslip/result mirror | Schema + fingerprint gated | `mirror_only` · `money_authority=external` · quarantine mismatches |
| Person identity merge (pre-hire) | Duplicate candidates | Preview / execute / reverse | **Never auto-merge** on additive migrate |
| Mailbox / durable email intake | CVs via email | Per-file **8 MB**; total **12 MB**; retries **5** | Quarantine + held intake; dry-run sync exists |

### 1.2 What does not exist

| Gap | Impact |
|---|---|
| Unified **Migration Center** | Operators hunt scattered UIs; Setup Console does not own data import |
| Millions-of-CVs / chunked enterprise CV job | Comment in code only; sync HTTP upload |
| ATS connectors (Workday/Taleo/etc.) | UI source labels are **provenance names only** |
| Candidate stage/status/history CSV | Cannot migrate pipeline state |
| Interview / assessment / notes / tags import | Missing entirely |
| ATS `external_id` / source-ID column on CV import | Only `source_ref`, checksum, batch id |
| Bulk CV **dry-run** | Upload commits registration immediately |
| Leave balance/history import with provenance | Missing |
| Shifts / templates import | Missing |
| Compensation CSV → draft contracts | Missing (draft→approve API exists; no file import) |
| Compliance document bulk + expiry backfill | Missing (seed `missing` rows; per-doc upload) |
| Customer onboarding-state import | Only internal Wave 3 checklist migration (controlled, dual-control) |
| Live vendor **SFTP** / object-storage drop folders for HR migration | Payroll adapter is synthetic CSV/SFTP **foundation**, not live vendor SFTP |
| Operator mobile bulk import | Marked unavailable |

### 1.3 Scale limits (hard numbers)

| Path | Cap | Mode |
|---|---|---|
| Bulk CV upload | 300 files / 250 MB | Synchronous request |
| Email intake file | 8 MB (12 MB total attachments) | Durable jobs |
| Employee roster | 1000 rows / 5 MB | Sync per-row commits |
| Org migration / bulk assign | 500 rows | Sync; pause/resume on migration |
| Attendance punches | 20 000 / 8 MB | Sync; flag-gated |
| Employee/app docs | 15 MB | Per upload |
| Semantic embed slice | ≤ 12 000 chars | Async after CV extract |

**Millions of CVs:** at 300/batch, 1 000 000 files ⇒ ~3 333 successful uploads **if** every request succeeds — unrealistic over HTTP sync, no chunked job, no object-storage ingest, no durable batch orchestrator for CV enterprise migration. **Not possible as a production operation today.**

---

## 2. Pre-hiring migration map

| Data | Import today? | Authority when imported |
|---|---|---|
| Candidates | Via CV files + optional metadata | Held (`needs_role` / `import_review`); not live pipeline |
| Millions of CVs / attachments | **No at scale** | N/A |
| Applications ↔ jobs | Role resolve on import; admit assigns job | Explicit admit → `ready_for_review`; folder hints never auto-assign |
| Stages / statuses | **No** historical stage CSV | Only held → admit lifecycle |
| Interviews | **No** | — |
| Assessments | **No** | — |
| Notes / tags | **No** | Source labels only |
| Consent / retention / deletion history | Import consent **missing**; inbound retention exists for email quarantine | Bulk CV retention weaker than inbound audit trail |
| Duplicate candidates | SHA-256 in-batch + existing CV; person merge UI separate | Checksum dups auto-flagged; **identity merge never automatic** |

**Auto-approve risk:** `company_auto_admit_imports` fails closed. When enabled, only **explicit role match** can skip Intake into `review_pending` — still not arbitrary stage authority.

---

## 3. Post-hiring migration map

| Data | Import today? | Authority when imported |
|---|---|---|
| Employees | CSV/XLSX roster (1000) | New hub keys only; no overwrite |
| Departments / branches / managers | Wave 4 migration batch | Org units may auto-create; manager_phone **mapped but not applied on commit** (gap); ambiguous → review |
| Contracts / compensation | **No CSV**; draft API / seed from offer | Draft only until `approve_contract` |
| Onboarding state | No customer import; Wave 3 internal only | Dual-control; no silent rewrite |
| Compliance docs + expiry | No bulk; seed `missing`; per-doc upload | HR reviewed ≠ government verified **forever** |
| Leave balances / history | **No** | Would need audited adjustment + provenance |
| Shifts / templates | **No** | — |
| Attendance history | Import V1 (flag) | Historical punches + derived attendance; reverseable; locked days skipped; **not** live ingest |
| Payroll IDs / results / payslips | External adapter import | Mirror-only; quarantine; Wathefni **not** money authority |

---

## 4. Product-rule compliance (authority honesty)

| Rule example | Current truth |
|---|---|
| Salary imports → draft compensation | **No salary CSV**; drafts exist and never auto-approve ✅ pattern |
| Documents ≠ government verified | Compliance freeze + findings honesty ✅ |
| Attendance imports historical / quarantined until approved | Import V1 writes attendance projections after preview/commit — **closer to historical SoR than quarantine**; reverse exists; flag-gated. Treat as **controlled historical authority**, not silent live ingest ✅/⚠️ |
| Leave balances need provenance | **No importer** — correct absence ✅ |
| Duplicates not auto-merged | Org migration + identity merge ✅; CV checksum auto-dedupe only ✅ |

**Standing bans (must remain):** Payroll money · CAPTURE_INGEST · AI assistant expansion · mobile widen · frozen-module contract changes · real customer migration in Wave 1.

---

## 5. Cross-cutting inspection

| Concern | Truth |
|---|---|
| File size / row limits | See §1.3 — real and enforced |
| Background jobs / batching / retry | CV extraction async (durable jobs, ~5 attempts on ingress); most post-hire imports **sync**; migration pause/resume exists; **no** enterprise chunked CV job |
| CV storage / parsing | `file_registry` + `candidate_documents` → extraction worker → semantic index async |
| Dedup / identity | CV checksum; org phone ambiguity → needs_review; person merge preview/execute/reverse |
| Source-ID preservation | Weak for ATS IDs; strong for checksum / batch / `source_ref` / export fingerprints |
| Dry-run / validation / exceptions | Strong on org migration, attendance, payroll, mailbox; **weak** on bulk CV (no dry-run) |
| Rollback / reconcile / audit | Org rollback + journal; attendance reverse; payroll reconcile; roster has audit counts but **no batch undo** |
| Tenant isolation | `company_code` on all paths; import smokes prove isolation |
| Privacy / consent / retention | Inbound retention mature; bulk CV consent/retention thinner |
| Search/index rebuild | Async semantic after extract; no “rebuild all after migration” API |
| Module boundaries | Entitlements + permissions on every importer; Import Center requires `pre_hiring` + `candidate.import` |

---

## 6. Do we need a Migration Center?

**Long-term: yes.** Operators need one place for:

- connector choice (upload / API / SFTP / object storage)
- mapping, dry-run, exception queue, commit, reconcile, rollback
- authority labels (draft / held / historical / mirror / needs_review)
- progress for multi-hour jobs
- module-aware visibility (aligned with Shell Wave 0)

**Near-term: no giant Center rebuild.** Existing importers already encode the right honesty patterns. A **Migration Foundation spine** should unify contracts first; UI Center comes after one durable batch path proves scale.

Closest today: Workforce “Migration & bulk” tab + Pre-hire Import Center + Attendance Import + External Payroll — **scattered, not first-class**.

---

## 7. Recommended architecture (long-term, simple)

```text
                    ┌─────────────────────────────┐
                    │     Migration Center UI      │
                    │  (module-aware · EN/AR)      │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Migration Foundation API  │
                    │  dry-run · map · commit ·   │
                    │  exception · reconcile ·    │
                    │  rollback · audit           │
                    └──────────────┬──────────────┘
           ┌───────────┬───────────┼───────────┬───────────┐
           ▼           ▼           ▼           ▼           ▼
        Upload      Signed      Object      SFTP       Webhook
        (CSV/ZIP)   API batch   storage     drop       / ATS
                                  (S3)      folder     events
                    └──────────────┬──────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │ Durable migration jobs      │
                    │ chunk · retry · lease · DLQ │
                    └──────────────┬──────────────┘
                                   ▼
              Module writers (never silent approve)
     held CV · draft contract · historical attendance
     mirror payroll · needs_review org · provenance leave
```

**Authority labels (required on every committed row):**

| Label | Meaning |
|---|---|
| `held` | Pre-hire intake; not pipeline |
| `draft` | Compensation/contract; needs approve |
| `historical` | Attendance/leave history with provenance |
| `mirror` | External payroll; not Wathefni money |
| `needs_review` | Ambiguous identity / mapping |
| `quarantined` | Failed validation; not SoR |

**Connectors:** start with **upload + object-storage staged drops**; API batch next; SFTP as adapter over the same job runner (payroll already sketched synthetic SFTP — reuse pattern, do not invent a second pipeline).

---

## 8. Smallest first implementation wave

### Name: **Migration Wave 1 — Foundation + Scale Path for CV Intake** (staging → WATHEFNI synthetic only)

**In scope (tight):**

1. **Migration Foundation contract** (shared): batch header, row status enum (`valid|invalid|duplicate|needs_review|committed|quarantined|skipped`), dry-run, exception list, audit event, tenant + module gates, authority label field.
2. **Chunked CV enterprise ingest (synthetic):** object-storage or staged server folder → durable jobs in chunks (e.g. 100–300 files) with retry/DLQ — reusing `process_bulk_cv_import` core (code already notes this reuse).
3. **Bulk CV dry-run + per-file size cap** (align toward email’s 8 MB honesty).
4. **Optional `external_id` / ATS candidate id** metadata column preserved on `import_items` / application raw JSON — no auto-merge.
5. **Prove:** 1k / 10k synthetic CVs; held-by-default; checksum dedupe; tenant isolation; no auto-admit unless explicit setting; residual 0; sibling freezes green.

**Explicitly out of Wave 1:**

- Real customer data  
- Millions in one go (prove 10k path first)  
- Full Migration Center UI (optional thin operator page OK)  
- Interview/assessment/notes/stage CSV  
- Leave / shifts / compensation CSV  
- Payroll money · Attendance CAPTURE_INGEST · Assistant Wave 3 · mobile  
- Opening Leave balances · government-verified docs  

**Why this first:** Millions-of-CVs is the clearest product ask that is **provably impossible** today; the codebase already has a reusable CV core and a “chunked enterprise job” comment. Foundation contract unblocks later post-hire importers without a dashboard rebuild.

### Suggested later waves (not started)

| Wave | Focus |
|---|---|
| 1-B | Production synthetic qualification of Wave 1 |
| 2 | Employee roster + org migration under Foundation (manager wire-up, batch undo) |
| 3 | Attendance historical import under Foundation (keep ingest off) |
| 4 | Leave opening balances with mandatory provenance (draft/historical) |
| 5 | Compensation CSV → **draft only** |
| 6 | Migration Center UI (module-aware shell) |
| 7 | SFTP/object-storage connectors for enterprise drops |

---

## 9. Performance & qualification plan (Wave 1)

| Tier | Target | Pass criteria |
|---|---|---|
| Local smoke | Contract + 50 synthetic CVs | Dry-run/commit; held statuses; checksum dupes |
| Staging | 1 000 then 10 000 synthetic CVs | Chunk jobs complete; retries; DLQ empty or explained; no auto-admit; EN/AR copy; freezes green |
| Prod synthetic | WATHEFNI only | Same as staging; residual 0; rollback of staged objects; no real customer files |
| Scale gate for “millions” | Separate wave after 10k green | Sustained chunk throughput + object-storage + monitoring — **not Wave 1** |

**Never:** import real customer CVs in Wave 1.

---

## 10. Risks

1. Treating Import Center labels (Workday/Taleo) as live connectors.  
2. Enabling auto-admit during migration → silent pipeline pollution.  
3. Confusing Attendance Import V1 with CAPTURE_INGEST.  
4. Org migration `manager_phone` mapped but not applied — managers silently missing.  
5. Employee roster no batch rollback — bad commit is hard to unwind.  
6. Building a Migration Center UI before durable jobs exist → pretty shell over sync timeouts.  
7. Leave/compensation imports without provenance → fake SoR.  
8. Cross-tenant checksum or phone collisions if company scoping regresses.

---

## 11. GO / NO-GO

| Scope | Verdict |
|---|---|
| Research / architecture (this audit) | **GO** |
| Migration Wave 1 Foundation + chunked CV (staging, synthetic) | **GO when authorized** |
| Production synthetic Wave 1-B | **NO-GO until Wave 1 staging green** |
| Real customer migration | **NO-GO** |
| Millions-of-CVs production cutover | **NO-GO** |
| Full Migration Center product | **NO-GO as first wave** |
| Leave / shifts / compensation / compliance bulk | **NO-GO in Wave 1** |
| Payroll money · Attendance ingest · Assistant expand · mobile | **NO-GO** |

---

## 12. Source anchors

- `wathefni-orchestrator/app.py` — `IMPORT_MAX_*`, `EMPLOYEE_IMPORT_MAX_*`, `process_bulk_cv_import`, employee import  
- `apps/wathefni-dashboard/src/components/ImportCenter.tsx`  
- `wathefni-orchestrator/employee_org_wave4.py` — migration dry-run/commit/rollback  
- `wathefni-orchestrator/attendance_import.py` — `MAX_BYTES` / `MAX_ROWS`  
- `wathefni-orchestrator/payroll_external_adapter_wave2a.py` — mirror-only import  
- `wathefni-orchestrator/candidate_identity.py` — merge preview/execute  
- `wathefni-orchestrator/inbound_retention_policy.py`  
- `ops/ATTENDANCE_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md`  
- `ops/PAYROLL_WAVE1_FOUNDATION_FREEZE.md` / Wave 2AD freezes  
- `ops/COMPLIANCE_WAVE1_FINDINGS_FREEZE.md`  
- `ops/COMPANY_SETUP_CONSOLE_AUDIT.md` (import outside Setup)  
- `ops/MODULE_AWARE_SHELL_WAVE0_FOCUSED_WORKFORCE_FREEZE.md`
