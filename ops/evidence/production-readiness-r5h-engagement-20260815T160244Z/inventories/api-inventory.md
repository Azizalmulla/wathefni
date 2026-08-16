# R5H API inventory

Dashboard prefixes: `/dashboard/engagement`, `/dashboard/posthire/engagement`

| Method | Path | Actor |
|---|---|---|
| GET | `/dashboard/engagement` | HR (`engagement.read`) |
| GET | `/dashboard/engagement/workspace` | HR (`engagement.read`) |
| GET/POST | `/dashboard/engagement/surveys` | HR read / `engagement.manage` |
| GET | `/dashboard/engagement/surveys/{survey_id}/versions` | HR |
| POST | `/dashboard/engagement/versions` | HR `engagement.manage` |
| GET/POST | `/dashboard/engagement/campaigns` | HR read / manage |
| GET | `/dashboard/engagement/campaigns/{campaign_id}` | HR |
| POST | `/dashboard/engagement/campaigns/{campaign_id}/launch` | HR `engagement.launch` |
| POST | `/dashboard/engagement/campaigns/{campaign_id}/close` | HR `engagement.launch` |
| GET | `/dashboard/engagement/campaigns/{campaign_id}/audience` | HR |
| GET | `/dashboard/engagement/campaigns/{campaign_id}/participation` | HR (status only) |
| GET | `/dashboard/engagement/campaigns/{campaign_id}/results` | HR |
| GET | `/dashboard/engagement/campaigns/{campaign_id}/segments` | HR |
| GET | `/dashboard/engagement/campaigns/{campaign_id}/enps/{question_id}` | HR |
| GET | `/dashboard/engagement/campaigns/{campaign_id}/free-text` | HR `engagement.manage` |
| POST | `/dashboard/engagement/campaigns/{campaign_id}/resolve` | HR (anonymous fail-closed) |
| GET | `/dashboard/engagement/campaigns/{campaign_id}/export` | HR `engagement.export` |
| GET/POST | `/dashboard/engagement/action-plans` | HR read / `engagement.actions` |
| GET | `/dashboard/engagement/history` | HR |
| POST | `/dashboard/engagement/assistant` | HR (read/explain) |
| GET | `/dashboard/engagement/manager` | Manager `engagement.manager` |
| GET | `/app/engagement` | Employee `view` |
| GET | `/app/engagement/surveys/{campaign_id}` | Employee `view` |
| POST | `/app/engagement/surveys/{campaign_id}/start` | Employee `submit` |
| POST | `/app/engagement/surveys/{campaign_id}/submit` | Employee `submit` |

Not registered: `/dashboard/mobile/engagement`.
