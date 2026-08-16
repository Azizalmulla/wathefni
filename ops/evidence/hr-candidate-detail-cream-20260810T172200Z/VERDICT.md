# HR Candidate detail — cream + honesty ship

Stamp: `20260810T172200Z`  
Surface: `/hr/candidates/[appKey]` · cream `CandidateReviewView` + localized route  
Ship: canary OTA **`1eb84033-38da-4772-8397-4d31c5cb2793`** · runtime 0.3.0 · iOS `019fecb6-43fd-72f7-906e-34d115825bd7`  
Backend: rankings honesty in `operator_mobile_data.mobile_candidate_rankings` · backup `/opt/wathefni/backups/hr-candidate-rankings-honesty-20260810T172200Z`

## Verdict: **PASS**

### Lock checklist

| Criterion | Result |
| --- | --- |
| Cream `PageScreen` + `HrPushedNav` | **PASS** |
| Stage chip tone from real stage | **PASS** |
| No `#appKey` chrome | **PASS** |
| CV empty EN/AR | **PASS** |
| Confirm action + consequence localized (known EN templates; unknown passthrough) | **PASS** |
| `already_decided` for terminal stages | **PASS** |
| Offer payload rendered when `current` present | **PASS** (Hamad draft offer) |
| SOD / invalidate / safe-back preserved | **PASS** |
| Rankings list=0 root cause | **PASS** — job-scoped ranking; empty success was dishonest; now `ranking_unavailable` + `requires_position` (no parallel list invented) |
| EN+AR physical copy matrix | **PASS** |

### Evidence

- `verify.txt` · `en-ar-physical.txt` · `nav-ergonomics.txt` · `deep-nav.txt` · `tsc.txt`
- `backend-deploy.txt` · `spine-probe.txt` · `ota-publish.log`
- Prior audit: `../hr-candidate-detail-qual-20260810T171500Z/`

### Not expanded

- No new candidate list authority; no hire/offer mutate from detail; no workflow redesign
