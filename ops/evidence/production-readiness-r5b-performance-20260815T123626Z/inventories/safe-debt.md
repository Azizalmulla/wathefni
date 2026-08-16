# R5B safe debt

Not blockers. Do not reopen Wave 4 authority to address these.

1. **HR Mobile is intentionally thin.** No mobile cycle admin, calibration admin, or full Goals workspace. Web-first by charter.
2. **Standalone `wathefni-hr-mobile` remains retired.** Cobundle is the ship target.
3. **Check-in / feedback create on HR Mobile** is not required for enable. Web + employee cover the journey.
4. **Competency authoring** stays in Setup / domain, not a second workspace editor.
5. **L&D integration** remains optional and unreleased. Development evidence links exist; learning completion does not close development.
6. **Talent card file** `Wave4PerformanceTalentPoliciesCard` stays on disk for R5C. Only `Wave4PerformancePoliciesCard` (`scope="performance"`) is mounted.
7. **Honesty copy mentions HiPo** to state the boundary ("a high rating is not HiPo"). No HiPo field, score, or Talent navigation is exposed.
8. **Early `except: pass` around other HTTP registrars** (probation / preboarding) is unchanged. Out of R5B scope unless those routes regress.
9. **Exports.** No Performance export endpoint shipped. If added later, re-prove tenant isolation and final-rating authorization.
10. **OTA vs native.** R5B Employee / HR Mobile changes are JS-only. Prefer `expo-updates` for canary; no new native build required for this slice.
11. **This stamp is not `PRODUCTION_READY`.** It authorises internal canary / owner review of the Performance product surface, not broad production rollout.
