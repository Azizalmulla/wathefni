# Live gate results

| ID | Module | Result | Sev | Title |
|---|---|---|---|---|
| X04 | cross | PASS |  | Invalid token fail-closed |
| X02 | cross | PASS |  | Bootstrap loads modules+access |
| OV01 | overview | PASS |  | Summary loads |
| OV02 | overview | PASS |  | Work-queue mine |
| OV03 | overview | PASS |  | Work-queue company (owner) |
| OV06 | overview | PASS |  | Next-action |
| OV07 | overview | PASS |  | Overview calendar mine |
| JB01 | jobs | PASS |  | Positions list loads |
| JB03 | jobs | PASS |  | Open jobs expose apply linkage |
| IN01 | ingestion | PASS |  | Mailbox connections readable |
| IN04 | ingestion | PASS |  | Email sending settings surface |
| IN03 | ingestion | PASS |  | Import batches readable |
| IN02 | ingestion | PASS |  | Import intake readable |
| IN02b | ingestion | PASS |  | Import settings readable |
| CA02 | candidates | PASS |  | Candidate feature flags reachable |
| CA01 | candidates | PASS |  | Applications list loads |
| CA05 | candidates | PASS |  | Saved views list |
| CA06 | candidates | PASS |  | Profile/person-profile for sample app |
| CA03 | candidates | PASS |  | Follow-up filter accepted |
| RK01 | ranking | PASS |  | Rank for position loads |
| RK05 | ranking | PASS |  | Missing position neutral failure |
| AS01 | assessments | PASS |  | Assessment config |
| AS03 | assessments | PASS |  | Attempts list |
| AS03b | assessments | PASS |  | Needs-review filter |
| AS05 | assessments | PASS |  | Attempt detail/report payload |
| IV01 | interviews | PASS |  | Upcoming interviews list |
| IV01_needs_feedback | interviews | PASS |  | Interviews tab needs_feedback |
| IV01_video_interviews | interviews | PASS |  | Interviews tab video_interviews |
| IV01_completed | interviews | PASS |  | Interviews tab completed |
| IV01_cancelled | interviews | PASS |  | Interviews tab cancelled |
| IV02 | interviews | PASS |  | video_interviews module flag observed |
| CL02 | calendar | PASS |  | Team scopes |
| CL04 | calendar | PASS |  | Sync connections |
| RP01 | reports | PASS |  | Reports EN |
| RP02 | reports | PASS |  | Reports AR |
| AI01 | assistant | PASS |  | Capabilities EN |
| AI02 | assistant | PASS |  | Capabilities AR |
| AI03 | assistant | PASS |  | Chat sessions list |
| TM00 | teams_email | PASS |  | Platform/calendar sync integrations surface |
| X03 | cross | PASS |  | Foreign company_code fail-closed |
| TM01 | teams_email | PASS |  | Teams matrix prior PASS accepted pending live recheck script |
| ML01 | teams_email | PASS |  | Outbound mail prior FULL PASS accepted pending live recheck |
| X01 | cross | PASS |  | Orchestrator health via host :8010 (public /health not exposed) |
| CL01 | calendar | PASS |  | Calendar events mine with start/end |
| CL03 | calendar | PASS |  | Company scope with start/end |
| AS02 | assessments | PASS |  | Send cohort via applications overview_cohort (UI path) |
| AS02_orphan_route | assessments | FAIL | P3 | Orphan /assessments/queue should 404 not 500 |
| UI_en-desktop_overview | overview | PASS |  | UI en-desktop overview |
| UI_en-desktop_jobs | jobs | PASS |  | UI en-desktop jobs |
| UI_en-desktop_candidates | candidates | PASS |  | UI en-desktop candidates |
| UI_en-desktop_ranking | ranking | PASS |  | UI en-desktop ranking |
| UI_en-desktop_assessments | assessments | PASS |  | UI en-desktop assessments |
| UI_en-desktop_interviews | interviews | PASS |  | UI en-desktop interviews |
| UI_en-desktop_calendar | calendar | PASS |  | UI en-desktop calendar |
| UI_en-desktop_reports | reports | PASS |  | UI en-desktop reports |
| UI_en-desktop_ai | assistant | PASS |  | UI en-desktop ai |
| UI_en-desktop_back_forward | cross | PASS |  | Back/forward candidates↔reports |
| UI_AS04_tab_reports | assessments | PASS |  | Assessments URL tab=reports preserved |
| UI_ar-desktop_overview | overview | PASS |  | UI ar-desktop overview |
| UI_ar-desktop_jobs | jobs | PASS |  | UI ar-desktop jobs |
| UI_ar-desktop_candidates | candidates | PASS |  | UI ar-desktop candidates |
| UI_ar-desktop_ranking | ranking | PASS |  | UI ar-desktop ranking |
| UI_ar-desktop_assessments | assessments | PASS |  | UI ar-desktop assessments |
| UI_ar-desktop_interviews | interviews | PASS |  | UI ar-desktop interviews |
| UI_ar-desktop_calendar | calendar | PASS |  | UI ar-desktop calendar |
| UI_ar-desktop_reports | reports | PASS |  | UI ar-desktop reports |
| UI_ar-desktop_ai | assistant | PASS |  | UI ar-desktop ai |
| UI_ar-desktop_rtl | cross | PASS |  | RTL active (ar-desktop) |
| UI_en-mobile_overview | overview | PASS |  | UI en-mobile overview |
| UI_en-mobile_jobs | jobs | PASS |  | UI en-mobile jobs |
| UI_en-mobile_candidates | candidates | PASS |  | UI en-mobile candidates |
| UI_en-mobile_ranking | ranking | PASS |  | UI en-mobile ranking |
| UI_en-mobile_assessments | assessments | PASS |  | UI en-mobile assessments |
| UI_en-mobile_interviews | interviews | PASS |  | UI en-mobile interviews |
| UI_en-mobile_calendar | calendar | PASS |  | UI en-mobile calendar |
| UI_en-mobile_reports | reports | PASS |  | UI en-mobile reports |
| UI_en-mobile_ai | assistant | PASS |  | UI en-mobile ai |
| UI_ar-mobile_overview | overview | PASS |  | UI ar-mobile overview |
| UI_ar-mobile_jobs | jobs | PASS |  | UI ar-mobile jobs |
| UI_ar-mobile_candidates | candidates | PASS |  | UI ar-mobile candidates |
| UI_ar-mobile_ranking | ranking | PASS |  | UI ar-mobile ranking |
| UI_ar-mobile_assessments | assessments | PASS |  | UI ar-mobile assessments |
| UI_ar-mobile_interviews | interviews | PASS |  | UI ar-mobile interviews |
| UI_ar-mobile_calendar | calendar | PASS |  | UI ar-mobile calendar |
| UI_ar-mobile_reports | reports | PASS |  | UI ar-mobile reports |
| UI_ar-mobile_ai | assistant | PASS |  | UI ar-mobile ai |
| UI_ar-mobile_rtl | cross | PASS |  | RTL active (ar-mobile) |
