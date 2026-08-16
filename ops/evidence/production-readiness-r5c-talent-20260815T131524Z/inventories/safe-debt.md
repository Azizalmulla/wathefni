# R5C safe debt

Not blockers. Do not reopen Wave 4 C5/C6 authority to address these.

1. **HR Mobile is intentionally absent.** Not an enable gate. No thin Talent admin queue shipped.
2. **Standalone `wathefni-hr-mobile` remains retired.** Employee-mobile cobundle is the ship target.
3. **9-box authoring stays thin.** Config + project endpoints exist; no decorative grid editor.
4. **Manager nomination request** notifies the authorized actor, never the nominee, so succession membership does not leak.
5. **L&D integration** remains optional and unreleased. Talent may show C3 development context only.
6. **Job Architecture** may be referenced internally when available later. No Talent-specific JA duplicate.
7. **Recruiting handoff** is an explicit payload (`kind=explicit_internal_opportunity`). A richer internal-apply UI can land later without silent `talent_pool` writes.
8. **Early `except: pass` around other HTTP registrars** is unchanged. Out of R5C scope unless those routes regress.
9. **Exports.** No Talent export endpoint shipped. If added later, re-prove tenant isolation and sensitive-field authorization.
10. **OTA vs native.** R5C Employee App changes are JS-only. Prefer `expo-updates` for canary; no new native build required for this slice.
11. **This stamp is not `PRODUCTION_READY`.** It authorises internal canary / owner review of the Talent product surface, not broad production rollout.
