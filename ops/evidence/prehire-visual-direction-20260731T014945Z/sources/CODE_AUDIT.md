# Source audit notes (pages without labeled screenshots)

Derived from `apps/wathefni-dashboard` on 2026-07-31 (visual only).

## App shell fork — App.tsx
- Overview: `bg-[#eee8da]` framed stage + dark sidebar treatment
- Other prehire pages: full-page cream radial gradient + light glass sidebar
- Unification requirement: one Overview-style dark framed shell for Assistant→Reports

## Jobs — pages/JobsPage.tsx + JobWorkspace.tsx
- Cream `#fffaf0` inventory section; closest content sibling to Overview
- Table/list density; status as black chips; shared Button create

## Candidates — pages/CandidatesPage.tsx
- Default Card (`bg-panel/88`) without `#fffaf0` override — cooler than Overview
- Densest filter bar (search, job, stage, advanced, saved views)

## Calendar — components/CalendarShell.tsx
- Cream board; OverviewCalendarPanel is peek of same language
- View toggles more square (`rounded-lg` / `rounded-xl`) than Overview pills

## Assessments — pages/AssessmentsPage.tsx
- Warm `#fffaf0` Cards; Button used as heavy tabs/cohort chips

## Ranking — pages/RankingPage.tsx
- Two warm Cards: job select + ranked articles; black Run/Rerun

## Reports — pages/ReportsPage.tsx
- Default untinted Cards — largest list-page drift from Overview desk

## Assistant — pages/AdminAIPage.tsx
- Glass chat (`bg-panel/82`, blur, shadow-premium, radius ~2.25rem)
- Distinct product surface vs Overview desk — restyle chrome only later
