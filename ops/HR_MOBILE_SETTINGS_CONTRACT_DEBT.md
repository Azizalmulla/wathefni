# HR mobile Settings — contract / UI debt

**Status:** Operator + device Settings wave shipped (cream/black, My Access, confirmed sign-out).  
**Boundary:** Not Setup Console. Not web Settings. No company writers.

## Known gaps

| Gap | Current behavior | Desired long-term |
| --- | --- | --- |
| Dual locale stores | Settings toggles both `@/i18n` (`wathefni.locale`) and `@hr/i18n` (`wathefni.hr.locale`) | Unify on one locale authority for the binary |
| Role fallback | Prefer `role_label`; map common `role` strings; else “Operator” | Backend always ships localized `role_label` |
| Workspace labels | HR / Hiring / Owner only when workspace.enabled | Optional finer “what I can decide” without raw feature keys |
| Sign-out UX | System `Alert.alert` confirms (More + Settings) | Optional shared cream confirm sheet |
| Employee Settings | Separate implementation by design | Keep separate; share patterns only intentionally |
| Push | Intentionally omitted | Separate operator push wave if needed |
| Device security card (`/app/device-security`) | Omitted on HR | Optional if product wants device metadata without employee API |
| Locale RTL skip-unlock-once | Not wired for HR | Mirror employee markers under `wathefni.hr.*` if needed |
| Phase 6 device screen-lock | Deferred (matches Employee) | Stay deferred |

Local PIN / Face ID / auto-lock shipped — see `ops/HR_MOBILE_LOCAL_LOCK_CONTRACT_DEBT.md`.

## Explicitly out of mobile scope

Roles · invites · modules · channels · WhatsApp · mailboxes · integrations · calendar · policies · Setup configuration · `/mobile/settings` write APIs.
