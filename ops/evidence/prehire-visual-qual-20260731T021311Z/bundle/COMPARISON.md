# Bundle-size comparison (local build vs production /var/www)

| Chunk | Local bytes | Prod bytes | Δ | Δ% |
|---|---:|---:|---:|---:|
| `AdminAIPage` | 15983 | 16008 | -25 | -0.16% |
| `AssessmentsPage` | 55432 | 55548 | -116 | -0.21% |
| `CalendarShell` | 29679 | 29592 | +87 | +0.29% |
| `CandidatesPage` | 12354 | 12300 | +54 | +0.44% |
| `InterviewsPage` | 31730 | 31740 | -10 | -0.03% |
| `JobsPage` | 37095 | 37079 | +16 | +0.04% |
| `RankingPage` | 9249 | 9310 | -61 | -0.66% |
| `ReportsPage` | 10721 | 10682 | +39 | +0.37% |
| `dashboard` | 214005 | 213425 | +580 | +0.27% |

Verdict: **PASS** — all key chunks within ±1% of production; visual chrome did not bloat the suite.
