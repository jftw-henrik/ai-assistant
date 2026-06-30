import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import get_settings

TRELLO_API_BASE = "https://api.trello.com/1"


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


def _auth_params() -> dict[str, str]:
    settings = get_settings()
    return {
        "key": settings.trello_api_key or "",
        "token": settings.trello_token or "",
    }


def _api_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    _require_trello_settings()
    query = {**_auth_params(), **(params or {})}
    url = f"{TRELLO_API_BASE}{path}?{urlencode(query)}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    request = Request(url, data=data, method=method, headers=headers)

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise TrelloError(f"Trello API error: {exc.code} {err_body}") from exc
    except URLError as exc:
        raise TrelloError(f"Trello API connection error: {exc.reason}") from exc


def _format_due_date(value: str) -> str:
    from datetime import UTC, datetime

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.hour or parsed.minute or parsed.second:
        return parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    due = parsed.date()
    return datetime(due.year, due.month, due.day, 12, 0, 0, tzinfo=UTC).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z"
    )


def get_board_id() -> str:
    settings = get_settings()
    if settings.trello_board_id:
        return settings.trello_board_id
    list_data = _api_request("GET", f"/lists/{settings.trello_list_id}", params={"fields": "idBoard"})
    board_id = list_data.get("idBoard")
    if not board_id:
        raise TrelloError("Could not resolve Trello board ID from list")
    return board_id


def fetch_board_snapshot() -> dict[str, Any]:
    """Fetch lists, open cards, and labels for the configured board."""
    board_id = get_board_id()
    lists = _api_request(
        "GET",
        f"/boards/{board_id}/lists",
        params={"fields": "name,id", "cards": "none"},
    )
    cards = _api_request(
        "GET",
        f"/boards/{board_id}/cards",
        params={
            "filter": "open",
            "fields": "name,desc,due,dateLastActivity,idList,labels,url",
            "label_fields": "name,color",
        },
    )
    labels = _api_request(
        "GET",
        f"/boards/{board_id}/labels",
        params={"fields": "name,color"},
    )
    list_by_id = {item["id"]: item["name"] for item in lists}
    compact_cards = []
    for card in cards:
        compact_cards.append(
            {
                "id": card["id"],
                "name": card["name"],
                "desc": card.get("desc") or "",
                "due": card.get("due"),
                "last_activity": card.get("dateLastActivity"),
                "list_id": card.get("idList"),
                "list_name": list_by_id.get(card.get("idList"), "Unknown"),
                "labels": [label.get("name") for label in card.get("labels", []) if label.get("name")],
                "url": card.get("url"),
            }
        )
    return {
        "board_id": board_id,
        "lists": [{"id": item["id"], "name": item["name"]} for item in lists],
        "labels": [{"id": item["id"], "name": item["name"], "color": item.get("color")} for item in labels if item.get("name")],
        "cards": compact_cards,
    }


def create_card(
    title: str,
    notes: str | None = None,
    due_date: str | None = None,
    *,
    list_id: str | None = None,
) -> str:
    """Create a card on a Trello list and return its ID."""
    settings = get_settings()
    params: dict[str, str] = {
        "idList": list_id or settings.trello_list_id or "",
        "name": title,
    }
    if notes:
        params["desc"] = notes
    if due_date:
        params["due"] = _format_due_date(due_date)
    payload = _api_request("POST", "/cards", params=params)
    card_id = payload.get("id")
    if not card_id:
        raise TrelloError("Trello API did not return a card ID")
    return card_id


def update_card_due(card_id: str, due_date: str) -> None:
    _api_request("PUT", f"/cards/{card_id}", params={"due": _format_due_date(due_date)})


def add_labels_to_card(card_id: str, label_ids: list[str]) -> None:
    for label_id in label_ids:
        _api_request("POST", f"/cards/{card_id}/idLabels", params={"value": label_id})


def get_or_create_label(board_id: str, label_name: str) -> str:
    labels = _api_request("GET", f"/boards/{board_id}/labels", params={"fields": "name"})
    for label in labels:
        if label.get("name", "").lower() == label_name.lower():
            return label["id"]
    created = _api_request(
        "POST",
        "/labels",
        params={"idBoard": board_id, "name": label_name, "color": "blue"},
    )
    return created["id"]


def resolve_list_id(board_snapshot: dict[str, Any], list_name: str) -> str:
    for item in board_snapshot["lists"]:
        if item["name"].lower() == list_name.lower():
            return item["id"]
    raise TrelloError(f"List not found on board: {list_name}")
