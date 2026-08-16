# Shell localization decision

Existing dashboard shell (`navItems`, `NAV_GROUP_LABELS`, `pageLabels`, Refresh/notice chrome) is English-only. There is no shared shell i18n system today.

For this closure pass:
- Wired Overview route title + subtitle into the existing recruiting locale (`overviewPageTitle` / `overviewPageSubtitle`) when `activePage === 'overview'`.
- Did **not** localize the sidebar or unrelated page titles (would be a broad shell redesign affecting every page).

Follow-up shared task: dashboard shell EN/AR/RTL localization for navigation groups, page titles, and common chrome.
