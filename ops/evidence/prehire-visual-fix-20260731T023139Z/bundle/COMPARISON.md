# Bundle-size comparison (local fix build vs production)

| Chunk | Local | Prod | Δ | Δ% |
|---|---:|---:|---:|---:|
| `dashboard` | 218730 | 213425 | +5305 | +2.49% |
| `JobsPage` | 36879 | 37079 | -200 | -0.54% |
| `CandidatesPage` | 13200 | 12300 | +900 | +7.32% |
| `InterviewsPage` | 31730 | 31740 | -10 | -0.03% |
| `CalendarShell` | 29679 | 29592 | +87 | +0.29% |
| `AssessmentsPage` | 55589 | 55548 | +41 | +0.07% |
| `RankingPage` | 9249 | 9310 | -61 | -0.66% |
| `ReportsPage` | 11416 | 10682 | +734 | +6.87% |
| `AdminAIPage` | 15983 | 16008 | -25 | -0.16% |

`dashboard` growth is AR shell chrome/localization strings from this correction pass.
