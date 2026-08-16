# Rollback proof

1. Executed `/opt/wathefni/backups/production-pre-onboarding-wave2b-20260802T011738Z/ROLLBACK.sh`
2. Restored app.py SHA `a73ee60b...` (Wave 1B); removed `onboarding_wave2.py`; removed synthetic-canary drop-in
3. Health OK after rollback
4. Re-deployed Wave 2B to SHA `d160e9b2...`
5. Re-ran synthetic canary to zero residue (see canary-post-rollback)
