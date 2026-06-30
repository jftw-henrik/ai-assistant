import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import get_settings


class TrelloError(Exception):
    """Raised when Trello API operations fail."""


def is_trello_available() -> bool:
    return all(
        os.getenv(name)
        for name in ("TRELLO_API_KEY", "TRELLO_TOKEN", "TRELLO_LIST_ID")
    )


def _require_trello_settings() -> None:
    if not is_trello_available():
        raise TrelloError(
            "Trello is not configured. Set TRELLO_API_KEY, TRELLO_TOKEN, and TRELLO_LIST_ID."
        )


def _format_due_date(value: str) -> str:
    from datetime import UTC, datetime

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.hour or parsed.minute or parsed.second:
        return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    due = parsed.date()
    return datetime(due.year, due.month, due.day, 12, 0, 0, tzinfo=UTC).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def create_card(
    title: str,
    notes: str | None = None,
    due_date: str | None = None,
) -> str:
    """Create a card on the configured Trello list and return its ID."""
    _require_trello_settings()
    settings = get_settings()

    params: dict[str, str] = {
        "key": settings.trello_api_key or "",
        "token": settings.trello_token or "",
        "idList": settings.trello_list_id or "",
        "name": title,
    }
    if notes:
        params["desc"] = notes
    if due_date:
        params["due"] = _format_due_date(due_date)

    url = f"https://api.trello.com/1/cards?{urlencode(params)}"
    request = Request(url, method="POST")

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise TrelloError(f"Trello API error: {exc.code} {body}") from exc
    except URLError as exc:
        raise TrelloError(f"Trello API connection error: {exc.reason}") from exc

    card_id = payload.get("id")
    if not card_id:
        raise TrelloError("Trello API did not return a card ID")

    return card_id
