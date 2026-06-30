import logging

from app.integrations.google_calendar import GoogleCalendarError, create_calendar_event, update_calendar_event
from app.integrations.trello import (
    TrelloError,
    add_labels_to_card,
    create_card,
    fetch_board_snapshot,
    get_board_id,
    get_or_create_label,
    resolve_list_id,
    update_card_due,
)
from app.models.trello_review import ApplySafeResult, BoardReviewResult, SafeAction

logger = logging.getLogger(__name__)

ALLOWED_SAFE_TYPES = {
    "create_card",
    "update_due_date",
    "add_labels",
    "create_calendar_event",
    "update_calendar_event",
}


class TrelloApplyError(Exception):
    """Raised when applying safe actions fails."""


def apply_safe_actions(review: BoardReviewResult) -> ApplySafeResult:
    result = ApplySafeResult(review_id=review.review_id)
    board_snapshot: dict | None = None
    board_id: str | None = None

    for action in review.safe_actions:
        if action.type not in ALLOWED_SAFE_TYPES:
            result.skipped.append(f"{action.type}: not allowed")
            continue

        try:
            if action.type in {"create_card", "add_labels"} and board_snapshot is None:
                board_snapshot = fetch_board_snapshot()
                board_id = board_snapshot["board_id"]
            applied_message = _apply_action(action, board_snapshot, board_id)
            result.applied.append(applied_message)
        except (TrelloError, GoogleCalendarError, ValueError) as exc:
            logger.exception("Failed to apply safe action %s", action.type)
            label = action.card_name or action.title or action.type
            result.errors.append(f"{action.type} ({label}): {exc}")
        except Exception as exc:
            logger.exception("Unexpected safe action failure %s", action.type)
            label = action.card_name or action.title or action.type
            result.errors.append(f"{action.type} ({label}): {exc}")

    return result


def _apply_action(
    action: SafeAction,
    board_snapshot: dict | None,
    board_id: str | None,
) -> str:
    if action.type == "create_card":
        if not action.title:
            raise ValueError("create_card requires title")
        list_id = None
        if action.list_name:
            if board_snapshot is None:
                board_snapshot = fetch_board_snapshot()
            list_id = resolve_list_id(board_snapshot, action.list_name)
        card_id = create_card(
            title=action.title,
            notes=action.notes,
            due_date=action.due_date,
            list_id=list_id,
        )
        return f"Created card '{action.title}' ({card_id})"

    if action.type == "update_due_date":
        if not action.card_id or not action.due_date:
            raise ValueError("update_due_date requires card_id and due_date")
        update_card_due(action.card_id, action.due_date)
        return f"Updated due date for '{action.card_name or action.card_id}'"

    if action.type == "add_labels":
        if not action.card_id or not action.labels:
            raise ValueError("add_labels requires card_id and labels")
        if board_id is None:
            board_id = get_board_id()
        label_ids = [get_or_create_label(board_id, name) for name in action.labels]
        add_labels_to_card(action.card_id, label_ids)
        return f"Added labels {', '.join(action.labels)} to '{action.card_name or action.card_id}'"

    if action.type == "create_calendar_event":
        if not action.title or not action.date:
            raise ValueError("create_calendar_event requires title and date")
        event_id = create_calendar_event(
            title=action.title,
            date=action.date,
            end_date=action.end_date,
        )
        return f"Created calendar event '{action.title}' ({event_id})"

    if action.type == "update_calendar_event":
        if not action.event_id or not action.title or not action.date:
            raise ValueError("update_calendar_event requires event_id, title, and date")
        event_id = update_calendar_event(
            event_id=action.event_id,
            title=action.title,
            date=action.date,
            end_date=action.end_date,
        )
        return f"Updated calendar event '{action.title}' ({event_id})"

    raise ValueError(f"Unsupported safe action: {action.type}")
