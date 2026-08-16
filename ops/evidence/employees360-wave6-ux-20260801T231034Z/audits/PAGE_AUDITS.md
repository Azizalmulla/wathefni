# Wave 6 — page-by-page audit decisions

**Stamp:** `20260801T231034Z`  
**Mode:** Local implementation + staging prove (no production deploy)

## Shared decisions
- Visual baseline: pre-hire cream/bone tokens (`wf-surface`, `#e8dfd0`, black primary pills sparingly for selected rails only).
- Personality: calm people/ops board — not Overview pastel metric grid.
- Authority: UI calls Wave 3/4/5 APIs only; approve ≠ apply; bank masked by default.
- Nav: hybrid — refine `employees`; add `workforce` hub with internal sections.

---

### 1. Employee directory (`employees`)
| | |
|---|---|
| **Purpose** | Find people; open profile; add/import roster |
| **Belongs** | Search, status, onboarding badge, primary roster actions |
| **Remove/move** | Giant repetitive cards → quiet board table; stats stay compact |
| **Primary action** | Open profile / Add employee (manage) |
| **Permissions** | `employees.read`; manage for add/import |
| **States** | loading, empty, search empty, left-roster toggle, error |
| **RTL/mobile** | Shared shell RTL; taller identity rows; cream avatar |

**Implemented:** board card, cream table, avatar initials, status column, `?employee=` deep-link.

### 2. Employee profile
| | |
|---|---|
| **Purpose** | One person: status, next action, modules, history |
| **Belongs** | Identity, next actions, assignment history, masked bank, module sections |
| **Remove/move** | `window.prompt` for status reason/reference → `ConfirmDialog.withReason` |
| **Primary action** | Clear next action / request status change |
| **Permissions** | Existing module gates unchanged |
| **States** | not found, pending approvals, left vs active |

**Implemented:** `AssignmentHistoryPanel` (current/scheduled/historical), `EssBankMaskPanel`, board tone header.

### 3. Employment & assignment history
| | |
|---|---|
| **Purpose** | Show Wave 4 slices without editing hub directly |
| **Belongs** | On profile; epochs labeled |
| **Primary action** | Read-only (mutations via Workforce / ESS) |

### 4. Organization structure (`workforce` → Organization)
| | |
|---|---|
| **Purpose** | Browse Wave 4 units; reconcile |
| **Primary action** | Reconcile (manage) |
| **Blocked** | `org_v4_disabled` / missing `employees.manage` |

### 5. Lifecycle actions (`workforce` → Lifecycle)
| | |
|---|---|
| **Purpose** | Pending lifecycle decide/cancel |
| **Primary action** | Approve / Reject (with reason) / Cancel |
| **Note** | Synthetic-only preserved; approval confirmation states apply is separate |

### 6. Jurisdiction & data remediation (`workforce` → Remediation)
| | |
|---|---|
| **Purpose** | Read-only queue of missing classification fields |
| **Primary action** | Understand next step (dual-control classification) — no auto-classify |
| **API** | `GET /employee-lifecycle/remediation` (Wave 6 thin read wrapper) |

### 7. Migration & bulk (`workforce` → Migration)
| | |
|---|---|
| **Purpose** | List batches; dry-run / commit / rollback with confirm |
| **Primary action** | Commit/rollback (destructive confirms) |
| **API** | `GET .../migration-batches` + existing POST actions |

### 8. ESS requests / approvals / conflicts (`workforce` → Requests)
| | |
|---|---|
| **Purpose** | HR queue for employee/manager self-service |
| **Belongs** | State, next approver, conflict banner, approve vs apply |
| **Sensitive** | Bank requests show mask notice |
| **Primary actions** | Approve; Apply (only when `approved`) |

---

## Reused shared components
`Card`/`PageIntro`/`StatusPill`/`SearchInput`/`Button`/`ConfirmDialog`/`Badge`/`LoadMoreBar` + tokens from `index.css`.

## Newly created
`posthire/employees360/chrome.tsx`, `WorkforcePage.tsx`, `ProfilePanels.tsx`; API clients in `api.ts`; thin staging-facing list endpoints for remediation + migration batches.
