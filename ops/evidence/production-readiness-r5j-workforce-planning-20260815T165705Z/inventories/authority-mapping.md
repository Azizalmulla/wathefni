# R5J authority mapping

| Product action | Canonical owner | Surface role |
|---|---|---|
| Planning cycle / plan | `workforce_planning_c7` | HTTP/HR Web adapter |
| Frozen baseline snapshot | C7 `freeze_baseline` | Surface supplies canonical actual population; never live rewrite |
| Scenario / version / revise | C7 | Independent scenarios; approved revisions create a new version |
| Assumptions | C7 `upsert_assumption` | Versioned; never silent Wave 5 turnover forecast |
| Demand (growth / replacement / vacancy / reduction / role-mix) | C7 `add_demand` | Explicit type/reason; no inferred demand |
| Planned positions / headcount | C7 | Planned ≠ actual position / vacancy / employment |
| Headcount projection | C7 `project_headcount` | Backend-authoritative, deterministic, explainable |
| Planned workforce cost | C7 `project_planned_cost` | Planned/estimated KWD; not payroll |
| Workforce gaps | C7 `compute_gap` | Definition-driven; no universal health score |
| Scenario comparison | C7 `compare_scenarios` | Compatible baseline/period/currency/definition only |
| Submit / approve | C7 | Approval ≠ actual workforce change |
| Execution handoff | C7 `create_execution_handoff` | Explicit; Recruiting OFF stays unexecuted; ON → one DRAFT requisition |
| Actual vs plan | C7 `actual_vs_plan` | Surface queries canonical actual; does not copy employees into WFP SoT |
| Job Profile / Grade / Level | `job_architecture_c1` | Hard dependency; WFP references only |
| Actual employment / headcount | Wave 5 / employment | WFP must never mutate |
| Compensation bands / assumptions | Compensation Planning C6 | Optional cost context only |
| Skills / capability / readiness | Talent | Optional context; no universal talent score |
| Draft requisition | Recruiting | Explicit authorized handoff only |
