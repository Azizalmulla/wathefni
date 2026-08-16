# R5H E2E journeys A–G

Proved on staging tenant `R5H71CB15` (`R5H_ENGAGEMENT_SURFACE_DB_PASS`, 87/0).

| Journey | Result |
|---|---|
| A Survey lifecycle | Anonymous version + 7-person audience → launch freezes version/audience → 3 submits below threshold (`scores=None`, `n=None`) → export suppressed → remaining submits meet threshold → scores present. Anonymous batches have no `employee_key`. No auto ER |
| B Complementary suppression | Department breakdown: ENG (4) and HR (3) both suppressed; suppressed cells have no `n` |
| C Privacy | Participation listed without answers. Admin cannot map E1 answers. `assert_no_respondent_answer_map` true. HTTP resolve of anonymous answers 403 |
| D Manager | 4-person team suppressed. Empty scope `company_wide=false`. Other 3-person manager scope suppressed. Manager raw anonymous answers denied. HTTP `/manager` with no org scope is not company-wide. Manager admin workspace 403 |
| E eNPS | Explicit 0–10 `enps_scale` computes. Arbitrary 1–5 rating returns `not_enps_question` |
| F Action plan | Plan created; `not_er_corrective_action`; `auto_created_er_case=false`; zero `er_cases`. Identified mode labeled distinctly from anonymous. Employee sees own surveys only; ZX isolated. Assistant aggregates ok; identify-respondent forbidden. Wave 5 typed facts only |
| G History / disable | Launched version pin unchanged after version 2 wording. History reconstructable. ER ON creates no ER cases. Disable blocks new campaigns, workspace `unavailable` / `counts=None`, campaigns retained, notifications suppressed after commit |

Also proved: HTTP unauthenticated not public; HR without `engagement.*` 403 is not empty-surveys; export without `engagement.export` is 403; export with permission has no respondent map; tenant isolation; employee no company analytics / scores.
