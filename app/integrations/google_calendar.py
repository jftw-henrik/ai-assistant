from datetime import datetime, timedelta
from functools import lru_cache
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
