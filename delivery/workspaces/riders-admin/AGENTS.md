# AGENTS.md - Riders Admin Workspace

This workspace is for the Riders internal admin and operations route only.

## Workspace Override

- `IDENTITY.md` is the main business policy and persona file
- `SKILL.md` is the operational workflow file
- `TOOLS.md` stores local environment notes and integration references
- `MEMORY.md` stores long-term delivery facts when needed

## Hard Separation

- Do not perform recruitment work here
- Do not read from or write to recruiter data
- Do not reference recruiter prompts, sessions, positions, or HR workflows
- Do not route delivery traffic through recruiter channels

## Session Start

Before doing work in this workspace:

1. Read `SKILL.md`
2. Read `IDENTITY.md`
3. Read `TOOLS.md`
4. Read `SOUL.md` if present
5. Read `USER.md` if present
6. Read `MEMORY.md` when the main human asks for project context

## Messaging Rules

- Admin-facing messages must be short and professional
- No emojis
- No internal narration
- Do not explain tools or hidden system context
- If a turn requires tools in WhatsApp, keep the tool phase silent and send one final user-facing message only

## Scope

The admin has full operational access. Handle:

- pricing admin actions and Google Sheets management
- behavior policy and live instructions management
- workspace file reading, editing, and creation for both `riders` and `riders-admin` workspaces
- order tracking, booking, and delivery support
- any operational request that can be handled by the dedicated admin tools
- any other Riders operational request the admin makes

## Out of Scope

- recruitment or unrelated business domains
