from datetime import UTC, datetime
from functools import lru_cache

from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

from app.integrations.google_auth import GoogleAuthError, build_google_service

DEFAULT_TASK_LIST = "@default"


class GoogleTasksError(Exception):
    """Raised when Google Tasks API operations fail."""


@lru_cache
def _get_tasks_service() -> Resource:
    try:
        return build_google_service("tasks", "v1")
    except GoogleAuthError as exc:
        raise GoogleTasksError(str(exc)) from exc


def _format_due_date(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    due = parsed.date()
    return datetime(due.year, due.month, due.day, tzinfo=UTC).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def create_task(
    title: str,
    notes: str | None = None,
    due_date: str | None = None,
) -> str:
    """Create a task in the default Google Tasks list and return its ID."""
    body: dict[str, str] = {"title": title}
    if notes:
        body["notes"] = notes
    if due_date:
        body["due"] = _format_due_date(due_date)

    try:
        task = (
            _get_tasks_service()
            .tasks()
            .insert(tasklist=DEFAULT_TASK_LIST, body=body)
            .execute()
        )
    except HttpError as exc:
        raise GoogleTasksError(f"Google Tasks API error: {exc}") from exc

    task_id = task.get("id")
    if not task_id:
        raise GoogleTasksError("Google Tasks API did not return a task ID")

    return task_id
