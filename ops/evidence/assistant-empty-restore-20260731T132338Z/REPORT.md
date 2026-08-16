# Assistant empty-state restore — production

**Stamp:** `20260731T132338Z`  
**Overall:** **PASS**  
**Live:** yes (orchestrator + dashboard)

---

## Root cause

The generic duplicated suggestion **“What can you help me with?”** was **not** an empty capability catalog.

It was an **error fallback** on the frontend:

1. `GET /dashboard/prehire/assistant/capabilities` existed in production `app.py`
2. It imported `build_dashboard_assistant_capabilities` from `tool_call_orchestrator`
3. That function was **missing** on the live orchestrator → **HTTP 500**
4. `App.tsx` caught the error and set `assistantEmptyState = null`
5. `AdminAIPage` then rendered a hard-coded `empty_fallback` string as both headline **and** a single chip

Classification of the before UI: **error fallback → hard-coded visual placeholder** (not loading, not a true empty catalog).

Before payload (`payload/before-en.json`):

```json
{"detail":{"error":"assistant_capabilities_failed","message":"cannot import name 'build_dashboard_assistant_capabilities' from 'tool_call_orchestrator' (...)"}}
```

---

## Production capability payload (after)

See `payload/after-en.json` / `payload/after-en-summary.json`.

| Field | Value |
|---|---|
| HTTP | **200** |
| `ok` | true |
| Offerable (sample) | `overview`, `jobs`, `candidates`, `interviews_schedule`, `calendar_events`, `assessments`, `ranking`, `reports`, plus post-hire (`posthire_*`) |
| Status for Overview→Reports | all `enabled_and_available` for this WATHEFNI owner |
| Empty chips (EN, max 6) | What should I work on today? · Create or update a job opening · Review candidates · Who needs an interview scheduled? · What's on the hiring calendar? · Who needs an assessment? |
| Headline | `Ask about hiring or your team.` (short when many modules) |

Frontend receives `empty_state` and renders chips via `data-testid="assistant-empty-chips"`. Click submits the real prompt (`afterClickHasUserMessage`).

---

## Fixes shipped

| Area | Change |
|---|---|
| Orchestrator | Deployed `build_dashboard_assistant_capabilities` + `empty_state_from_catalog` / chip helpers |
| Catalog chips | Include Overview/Jobs/Calendar; no fake chip when nothing offerable |
| FE states | Distinct `loading` / `error` (+Retry) / `none` / capability chips — no error→placeholder chip |
| Layout | Assistant fills frame; transcript scrolls; composer sticky; nav rows fixed `h-11` + truncate |
| EN/AR/RTL | Preserved (`dir=rtl` on Assistant in AR) |

---

## Gates

| Gate | Result |
|---|---|
| Before = API 500 + generic chip | **PASS** (`screenshots/before/`, `verify/before-probe.json`) |
| After payload 200 + offerable catalog | **PASS** |
| Capability-driven chips (not generic duplicate) | **PASS** |
| Click chip submits prompt | **PASS** |
| EN/AR screenshots | **PASS** (`screenshots/after/`) |
| Nav Assistant height == Jobs | **PASS** (44px / 44px) |
| Composer visible; page scroll excess &lt; 80 | **PASS** (excess ≈ 8) |
| Unit empty-state matrix | **PASS** |
| Health after deploy | **200** |

---

## Backup

`/opt/wathefni/backups/production-pre-assistant-empty-20260731T132338Z/ROLLBACK.sh`

Screenshots: `screenshots/before/assistant-en-desktop.png` · `screenshots/after/assistant-en-desktop.png` · `assistant-ar-desktop.png`
