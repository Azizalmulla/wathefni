# Bundle-size comparison (local mobile-nav build vs production)

| Chunk | Local | Prod | Δ | Δ% |
|---|---:|---:|---:|---:|
| `dashboard` | 221411 | 213425 | +7986 | +3.74% |
| `JobsPage` | 36879 | 37079 | -200 | -0.54% |
| `CandidatesPage` | 13200 | 12300 | +900 | +7.32% |
| `InterviewsPage` | 31730 | 31740 | -10 | -0.03% |
| `CalendarShell` | 29679 | 29592 | +87 | +0.29% |
| `AssessmentsPage` | 55589 | 55548 | +41 | +0.07% |
| `RankingPage` | 9249 | 9310 | -61 | -0.66% |
| `ReportsPage` | 11416 | 10682 | +734 | +6.87% |
| `AdminAIPage` | 15983 | 16008 | -25 | -0.16% |

Local `dashboard` growth is sticky PRE-HIRING active chip + mobile rail + RTL `min-w-0` overflow containment in the framed shell. Page chunks unchanged.
