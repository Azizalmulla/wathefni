"""Provider-neutral Calendar sync adapter interface (C5).

Calendar domain code must not import Google/Microsoft SDKs. Adapters live here.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class CalendarSyncAdapter(Protocol):
    provider_key: str

    def healthcheck(self, connection: Mapping[str, Any]) -> dict[str, Any]:
        ...

    def upsert_event(
        self,
        *,
        connection: Mapping[str, Any],
        binding: Mapping[str, Any] | None,
        external_event: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Create or update external event. Must return provider_event_id on success."""
        ...

    def cancel_event(
        self,
        *,
        connection: Mapping[str, Any],
        binding: Mapping[str, Any],
    ) -> dict[str, Any]:
        ...


def get_adapter(provider_key: str) -> CalendarSyncAdapter:
    key = str(provider_key or "").strip().lower()
    if key in {"google", "google_workspace"}:
        from calendar_sync_google import GoogleCalendarSyncAdapter

        return GoogleCalendarSyncAdapter()
    if key in {"microsoft", "microsoft_365", "outlook"}:
        from calendar_sync_microsoft import MicrosoftCalendarSyncAdapter

        return MicrosoftCalendarSyncAdapter()
    raise ValueError(f"unsupported_sync_provider:{key}")
