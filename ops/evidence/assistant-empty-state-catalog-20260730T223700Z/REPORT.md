# Assistant empty-state — capability-catalog driven

**Stamp:** `20260730T223700Z`  
**Verdict:** **PASS**

## Goal

Empty-state headline, module list, and prompt chips use the same live `assistant_capability_catalog` authority as Assistant tools. No advertising of disabled, unauthorized, or unconfigured modules.

## Changes

| Area | Path |
|---|---|
| Catalog empty-state helpers | `wathefni-orchestrator/assistant_capability_catalog.py` — `empty_modules_from_catalog`, `empty_headline_from_catalog`, `empty_state_from_catalog` (chips already existed) |
| Dashboard catalog builder | `wathefni-orchestrator/tool_call_orchestrator.py` — `build_dashboard_assistant_capabilities` |
| API | `GET /dashboard/prehire/assistant/capabilities?locale=` in `app.py` |
| FE fetch | `apps/wathefni-dashboard/src/lib/api.ts` — `getAssistantCapabilities` |
| FE types | `apps/wathefni-dashboard/src/types.ts` — `AssistantEmptyState`, `AssistantCapabilitiesResponse` |
| Empty UI | `AdminAIPage.tsx` — consumes `emptyState` (headline + modules + chips); removed client `assistantPromptChips` |
| Wiring | `App.tsx` — loads catalog when Assistant page is open; refreshes on locale / modules / access change |

## Behaviour

- Offer only capabilities with `status=enabled_and_available`
- Headline + module list built from offerable groups only
- Chips from `empty_prompt_chips_from_catalog`
- Neutral EN/AR fallback when nothing is offerable: “What can you help me with?” / “بماذا يمكنني المساعدة؟”
- RTL preserved via existing `dir={isAr ? 'rtl' : 'ltr'}`
- No visual redesign beyond a subtle module-list line under the headline

## Tests

| Suite | Result |
|---|---|
| `python3 test_assistant_empty_state_catalog.py` | **PASS** — hiring-only, mixed pre/post-hire, disabled payroll, restricted recruiter, enabled-but-unconfigured providers, neutral fallback, EN/AR parity |
| `python3 test_assistant_capability_catalog.py` | **PASS** |
| `vitest AdminAIUxContract.test.tsx` | **PASS** (6) — includes catalog-driven empty-state contract |

## Overall

**PASS** — empty-state copy/chips are catalog-driven; unauthorized/disabled/unconfigured modules are not advertised.
