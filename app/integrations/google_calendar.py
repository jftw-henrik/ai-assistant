import os
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

from app.config import get_settings
from app.integrations.google_auth import GoogleAuthError, build_google_service

DEFAULT_REMINDERS = [
    {"method": "popup", "minutes": 10080},
    {"method": "popup", "minutes": 1440},
    {"method": "popup", "minutes": 60},
]


class GoogleCalendarError(Exception):
    """Raised when Google Calendar API operations fail."""


def is_google_calendar_available() -> bool:
    return all(
        os.getenv(name)
        for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
    )


@lru_cache
def _get_calendar_service() -> Resource:
    try:
        return build_google_service("calendar", "v3")
    except GoogleAuthError as exc:
        raise GoogleCalendarError(str(exc)) from exc


def _parse_datetime(value: str, timezone: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    tz = ZoneInfo(timezone)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def _format_event_datetime(dt: datetime, timezone: str) -> dict[str, str]:
    local = dt.astimezone(ZoneInfo(timezone))
    return {
        "dateTime": local.strftime("%Y-%m-%dT%H:%M:%S"),
        "timeZone": timezone,
    }


def create_calendar_event(
    title: str,
    date: str,
    end_date: str | None = None,
) -> str:
    """Create an event in the user's primary Google Calendar and return its ID."""
    settings = get_settings()
    timezone = settings.google_calendar_timezone

    start = _parse_datetime(date, timezone)
    end = _parse_datetime(end_date, timezone) if end_date else start + timedelta(hours=1)

    body = {
        "summary": title,
        "start": _format_event_datetime(start, timezone),
        "end": _format_event_datetime(end, timezone),
        "visibility": "private",
        "reminders": {
            "useDefault": False,
            "overrides": DEFAULT_REMINDERS,
        },
    }

    try:
        event = (
            _get_calendar_service()
            .events()
            .insert(calendarId=settings.google_calendar_id, body=body)
            .execute()
        )
    except HttpError as exc:
        raise GoogleCalendarError(f"Google Calendar API error: {exc}") from exc

    event_id = event.get("id")
    if not event_id:
        raise GoogleCalendarError("Google Calendar API did not return an event ID")

    return event_id


def update_calendar_event(
    event_id: str,
    title: str,
    date: str,
    end_date: str | None = None,
) -> str:
    """Update an existing Google Calendar event and return its ID."""
    settings = get_settings()
    timezone = settings.google_calendar_timezone

    start = _parse_datetime(date, timezone)
    end = _parse_datetime(end_date, timezone) if end_date else start + timedelta(hours=1)

    body = {
        "summary": title,
        "start": _format_event_datetime(start, timezone),
        "end": _format_event_datetime(end, timezone),
        "visibility": "private",
        "reminders": {
            "useDefault": False,
            "overrides": DEFAULT_REMINDERS,
        },
    }

    try:
        event = (
            _get_calendar_service()
            .events()
            .update(calendarId=settings.google_calendar_id, eventId=event_id, body=body)
            .execute()
        )
    except HttpError as exc:
        raise GoogleCalendarError(f"Google Calendar API error: {exc}") from exc

    updated_id = event.get("id")
    if not updated_id:
        raise GoogleCalendarError("Google Calendar API did not return an event ID")

    return updated_id


def _compact_event(event: dict[str, Any], timezone: str) -> dict[str, Any]:
    start = event.get("start", {})
    end = event.get("end", {})
    start_value = start.get("dateTime") or start.get("date")
    end_value = end.get("dateTime") or end.get("date")
    return {
        "id": event.get("id"),
        "title": event.get("summary", "(No title)"),
        "start": start_value,
        "end": end_value,
        "all_day": "date" in start and "dateTime" not in start,
        "timezone": timezone,
        "description": event.get("description") or "",
        "visibility": event.get("visibility", "default"),
        "status": event.get("status", "confirmed"),
        "location": event.get("location") or "",
        "html_link": event.get("htmlLink"),
    }


def list_upcoming_events(*, days: int = 30) -> list[dict[str, Any]]:
    """List upcoming calendar events for the next N days (read-only)."""
    settings = get_settings()
    timezone = settings.google_calendar_timezone
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    end = now + timedelta(days=days)

    try:
        result = (
            _get_calendar_service()
            .events()
            .list(
                calendarId=settings.google_calendar_id,
                timeMin=now.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleCalendarError(f"Google Calendar API error: {exc}") from exc

    return [_compact_event(item, timezone) for item in result.get("items", [])]


def list_today_events() -> list[dict[str, Any]]:
    """List today's events from the configured Google Calendar (read-only)."""
    settings = get_settings()
    timezone = settings.google_calendar_timezone
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    try:
        result = (
            _get_calendar_service()
            .events()
            .list(
                calendarId=settings.google_calendar_id,
                timeMin=start_of_day.isoformat(),
                timeMax=end_of_day.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except HttpError as exc:
        raise GoogleCalendarError(f"Google Calendar API error: {exc}") from exc

    return [_compact_event(item, timezone) for item in result.get("items", [])]
