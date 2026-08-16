# PT1 evidence matrices

## Authority / reuse map

| Concept | Canonical owner | PT1 overlay | Forbidden |
|---|---|---|---|
| Objective / KR / measure / progress | C1 `performance_goals_c1` | Cycle membership, visibility, updates | Second OKR tables, frontend % |
| Alignment links | C1 `perf_alignment_links` | Tree, history events | Score inheritance |
| Review cycle | C2 `perf_review_cycles` | None | Reusing review cycles as OKR cycles |
| Check-in | C3 `perf_check_ins` | Optional link from OKR update | Progress mutation |
| Talent profile / skills / potential | C5 | Evidence pointers only | Classification, copied ratings |
| HiPo / succession / readiness | C6 | None | Any write from PT1 |
| Analytics | Wave 5 | None | Second analytics engine |

## OKR cycle contract

- Table: `perf_okr_cycles`
- Statuses: `draft` → `active` → `closed`
- Fields: name EN/AR, period start/end, scope, org unit, visibility policy, version, history
- Constraint: `metadata.review_cycle_id` must be null
- Honesty: `okr_cycle_is_not_review_cycle = true`

## Alignment contract

- Child `from` contributes to parent `to`
- Tree: Company → Department → Team → Individual where configured
- Orphans allowed
- Cross-functional links allowed only through C1 link kinds
- `inherits_score = false` always
- Hidden nodes omitted — following a tree is not a permission bypass

## Evidence-reference schema

`talent_evidence_refs` unique on `(company, source_authority, source_id, source_version, employee_key)`

| Field | Role |
|---|---|
| tenant / employee_key | Isolation |
| source_module / source_authority / source_id / source_version | Pointer |
| as_of | Effective time |
| evidence_kind | Kind |
| provenance_class | Provenance |
| consume_contract | Admission |
| payload_hash | Integrity marker |
| claimed_not_verified | Claimed skill guard |
| classification_input_eligible | AI / claim guard |
| source_module_disabled / inaccessible | Lifecycle |

Default: pointer / read-through. `copied_canonical_rating` is forbidden in metadata.

## Provenance matrix

| Class | Meaning | Classification input |
|---|---|---|
| SYSTEM-DERIVED | Canonical module fact | Eligible only if consume contract admits it |
| MANAGER-ASSESSED | Manager judgment | Eligible if admitted |
| HR-ASSESSED | HR judgment | Eligible if admitted |
| EMPLOYEE-DECLARED | Employee claim | Display/context; claimed ≠ verified |
| AI-SYNTHESIZED | Explanation only | **Never** |

Contradictions are retained. The index does not resolve disagreement.

## Consume-contract matrix

| Contract | Default | PT1 use |
|---|---|---|
| `okr_as_talent_evidence_v1` | OFF | Explicit Setup opt-in |
| `performance_outcome_as_evidence_v1` | OFF unless frozen C5 consume is on | Existing exception |
| `learning_*` | OFF | Not activated in PT1 |
| `ja_assignment_as_evidence_v1` | OFF | Not activated in PT1 |
| `assessment_as_evidence_v1` | OFF | Not activated in PT1 |
| `recruiting_import_at_hire_v1` | OFF | Not activated in PT1 |
| `claimed_skill_display_v1` | ON | Display only |
| `talent_native_v1` | Native Talent objects | Not a cross-module consume contract |

## Permission matrix

| Actor | Sees |
|---|---|
| Talent read + source read | Full pointer |
| Talent read without source read | Hidden, or existence-only if sensitive and explicitly allowed |
| No Talent read | Denied |
| Other tenant | Empty |

Alignment visibility: owner, manager scope, org-unit, or configured company-wide. Server enforced.
