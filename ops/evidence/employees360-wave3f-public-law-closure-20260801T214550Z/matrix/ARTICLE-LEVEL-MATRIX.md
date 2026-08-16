# Article-level public-law verification matrix — Wave 3F

**Stamp:** `20260801T214550Z`  
**Primary Arabic source:** e.gov / MOJ Law No. 6 of 2010 PDF — SHA256 `20eac58834489098d86271cfc6df9926adfe3fcc9607c47531247e6a56d3f326`  
**English reading aid:** Official Gazette Issue 963 extract — SHA256 `aaed5c6e02a03df4bfdcf035ba1befb9ece3c96d635c5a947f0c5ae929a70fe0`  
**Disclaimer:** Not legal advice. Wathefni does not decide lawfulness or compute monetary entitlements.

Classification legend:
- `mandatory_statutory` — encodeable statutory behaviour
- `configurable_company_policy` — company policy within product
- `case_specific_human` — human legal judgment; software must not decide
- `payroll_monetary` — Payroll owns calculation
- `unresolved_disabled` — safest disabled / manual fallback

| Topic | Exact source & article | AR verify | EN verify | Archived hash (primary) | Rule summary | Wathefni product implication | Confidence | Ambiguity | Classification |
|---|---|---|---|---|---|---|---|---|---|
| Law scope | Law 6/2010 Arts. 2–4; PNG p.02 | PASS visual | PASS Gazette | `20eac588…d326` | Applies to private sector; marine/oil residual | `jurisdiction_mode=kuwait_private_sector_only` | High | Oil/marine residual rarely productized | mandatory_statutory |
| Excluded workers | Art. 5; PNG p.02 | PASS | PASS | `20eac588…d326` | Excludes workers under other laws + domestic workers | Out of Employees 360 private-sector lifecycle scope | High | Boundary cases (other statutes) need human | case_specific_human |
| Minimum rights floor | Art. 6; PNG p.02 | PASS | PASS | `20eac588…d326` | Law is minimum; better contract terms prevail | Do not encode contract reductions below floor; company may be more generous | High | — | mandatory_statutory / configurable_company_policy |
| Unlimited notice monthly | Art. 44(a); PNG p.09 | PASS | PASS | `20eac588…d326` | 3 months’ notice for monthly-paid unlimited contracts | Optional labeled hint 90 days only if `show_notice_hints` **and** fields complete | High | Calendar vs working-month ops | mandatory_statutory (guidance); UI configurable |
| Unlimited notice other pay | Art. 44(b); PNG p.09 | PASS | PASS | `20eac588…d326` | 1 month for other pay frequencies | Optional labeled hint 30 days under same eligibility | High | — | mandatory_statutory (guidance); UI configurable |
| Notice compensation boundary | Art. 44 body; PNG p.09–10 | PASS | PASS | `20eac588…d326` | Fail to give notice → pay remuneration for notice period | **No** E360 amount; settlement inputs only → Payroll | High | What counts as “remuneration” for period → Payroll | payroll_monetary |
| Job-search time | Art. 44(c); PNG p.10 | PASS | PASS | `20eac588…d326` | During employer notice: 1 day or 8h/week paid | Not auto-scheduled; HR ops manual | High | Scheduling UX | case_specific_human |
| Garden leave / exempt from work | Art. 44(d); PNG p.10 | PASS | PASS | `20eac588…d326` | Employer may exempt worker; period counts as service; pay entitlements | No garden-leave pay calculator; LWD + effective are HR inputs | High | — | case_specific_human / payroll_monetary (pay) |
| Fixed-term early end | Art. 47; PNG p.10 | PASS | PASS | `20eac588…d326` | Wrongful early termination → damages ≤ remaining-term pay | Require `contract_type=fixed_term`; **no** Art. 44 hints; no damages math | High | “Unrightfully” is human judgment | case_specific_human / payroll_monetary |
| Probation | Art. 32; PNG p.07 | PASS | PASS | `20eac588…d326` | ≤100 working days; terminate without notice; employer still pays EOSB for period; once/employer | Require `probation_status` (+ dates if active); hide notice hints when active; EOSB → Payroll | High | Working-day calendar | mandatory_statutory (no-notice path); payroll_monetary (EOSB) |
| Summary dismissal categories | Art. 41(a)/(b); PNG p.09 | PASS | PASS | `20eac588…d326` | (a) no notice/comp/benefit; (b) keep EOSB; appeal; Ministry notify | Case classes `summary_dismissal_41a/41b`; **exceptional manual**; software never decides lawfulness | High | Grounds fit is litigation | case_specific_human |
| Abandonment | Art. 42; PNG p.09 | PASS | PASS | `20eac588…d326` | 7 consecutive / 20 separate days → deemed resignation; Art. 53 EOSB | `abandonment_42` exceptional; evidence + escalation note | High | Excuse validity | case_specific_human |
| Worker summary exit | Art. 48; PNG p.10 | PASS | PASS | `20eac588…d326` | Worker may exit without notice with EOSB on listed grounds | `worker_summary_exit_48` exceptional manual | High | Grounds proof | case_specific_human |
| Death / disability | Art. 49; PNG p.10 | PASS | PASS | `20eac588…d326` | Contract ends on death / incapacity / sick-leave exhaustion | `death_disability_49` exceptional; medical evidence human | High | — | case_specific_human |
| Employer status end | Art. 50; PNG p.10 | PASS | PASS | `20eac588…d326` | Bankruptcy / permanent closure; transfer keeps contracts | `employer_status_50` exceptional | Medium–High | Transfer continuity ops | case_specific_human |
| EOSB base formulas | Arts. 51–53; PNG p.11 | PASS (2010 text) | PASS | `20eac588…d326` | Tiered EOSB by pay type; resignation fractions | **Payroll exclusive**; E360 inputs-only packet | High on ownership; Medium on 2018 amendment Arabic | Law 17/2018 not in base PDF | payroll_monetary |
| EOSB Law 17/2018 | NATLEX KWT-2018-L-108307 (secondary) | NOT retrieved (403) | Abstract only | see `NATLEX-CITATION-NOTE.md` | Amends Art. 51 re Kuwaiti nationals / PIFSS | Payroll owns; E360 must not encode | Low on exact Arabic wording | Missing Official Gazette PDF | payroll_monetary / unresolved_disabled (in E360) |
| Annual-leave cash | Art. 73; PNG p.15 | PASS | PASS | `20eac588…d326` | Cash for accumulated annual leave on contract end | Leave balances as settlement **inputs**; Payroll calculates | High | Accrual engine outside E360 | payroll_monetary |
| Service certificate | Art. 54; PNG p.11 | PASS | PASS | `20eac588…d326` | Certificate: duration, position, last remuneration; no harmful wording; return docs | Default pending `employee_lifecycle_service_certificates` workflow | High | Issuance content human-authored | mandatory_statutory (workflow) |
| Personnel file | Art. 80; PNG p.16 | PASS | PASS | `20eac588…d326` | Maintain file incl. contract, leaves, EOS date/reasons, return receipts | Retain mode; store termination classification + dates | High | Multi-year schedule beyond litigation | mandatory_statutory |
| Limitation / retention floor | Art. 144; PNG p.25 | PASS | PASS | `20eac588…d326` | Worker suits generally not heard after **one year** from contract end | `document_retention_floor_days=365`; **no auto-purge** | High for floor; Medium for longer retention | Exact multi-year schedule not in public text → retain | mandatory_statutory (floor) / configurable (longer) |
| Cancel before effective | Product + Art. 44 context | N/A (product) | N/A | policy pack | Cancel scheduled termination before effective preserves same employment | `cancel_scheduled` case; dual approval | High (product) | Legal effect of notice withdrawal case-specific | configurable_company_policy / case_specific_human |
| Reinstatement vs rehire | No clear continuous-service reinstate statute located | N/A | N/A | policy pack | Default: post-effective reinstate **disabled**; true rehire | `allow_reinstate_after_effective=false`; `rehire` new employment | High for conservatism | Visa/indemnity continuity ambiguous | unresolved_disabled (reinstate) / configurable opt-in |

## Notice guidance eligibility (fail closed)

Hints may appear **only** when all are true:
1. `show_notice_hints=true` (default **false**)
2. `contract_type=unlimited`
3. `probation_status` ≠ `active`
4. `pay_frequency` in `{monthly, other}`
5. `termination_case_class` not in exceptional set

Otherwise UI stays hidden / manual review.
