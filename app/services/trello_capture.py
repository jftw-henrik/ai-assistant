import json
import logging
import re
from datetime import date

from groq import APIError as GroqAPIError
from groq import Groq

from app.config import Settings
from app.integrations.google_calendar import GoogleCalendarError, create_calendar_event
from app.integrations.trello import (
    TrelloError,
    add_comment,
    archive_card,
    create_card,
    fetch_board_snapshot,
    find_list_id,
    move_card,
    resolve_list_id_or_create,
    update_card,
)
from app.db import repository as db
from app.models.trello_capture import CaptureDecision, CaptureResult

logger = logging.getLogger(__name__)

DONE_KEYWORDS = ("done", "klart", "fixed", "completed", "finished", "färdig", "klar")
ARCHIVE_KEYWORDS = ("archive", "archived", "ta bort", "rensa")
DEFAULT_LIST = "To Do"
DONE_LIST = "Done"

ROUTING_PROMPT = """You route voice/text capture into Trello actions.

Today's date: {today}

You receive:
1. user input
2. current board lists and open cards

Classify input as one of:
- new_task
- idea
- project
- update (add info to existing card)
- completed (mark work finished)
- deadline (has date/time/deadline/appointment/meeting)

Return ONLY valid JSON:
{{
  "input_type": "new_task|idea|project|update|completed|deadline",
  "action": "create_card|update_card|comment_card|move_to_done|archive_card",
  "reason": "short explanation",
  "match_confidence": "high|low|none",
  "matched_card_id": "id or null",
  "matched_card_name": "name or null",
  "list_name": "target list name",
  "create_list_if_missing": false,
  "title": "card or event title",
  "notes": "optional notes/description",
  "comment": "comment text for update/comment actions",
  "due_date": "ISO 8601 due date if relevant",
  "calendar_date": "ISO 8601 datetime if calendar event needed",
  "calendar_end_date": "optional ISO 8601 end datetime"
}}

List selection rules:
- Work: client/work/music/professional work tasks
- FIRMOR: company/admin/accounting/business tasks
- To Do: personal/general tasks and fallback when uncertain
- In Progress: only for clearly active ongoing work
- Done: only for completed tasks (move_to_done / archive_card)

Matching rules:
- Match existing cards when the user clearly refers to the same task.
- set match_confidence=high only when very confident.
- If uncertain, action=create_card, list_name=To Do, matched_card_id=null, match_confidence=none.

Action rules:
- update/comment on existing card only when match_confidence=high.
- completed + done/klart/fixed/completed -> move_to_done when match is high, else create_card in To Do.
- archive/ta bort/rensa only when user clearly wants archive AND task is clearly completed.
- deadline/date/time -> set due_date and calendar_date; action usually create_card or update_card.
- idea/project/new_task without date -> create_card in best list.
- Never choose archive_card unless archive intent is explicit.

create_list_if_missing:
- true only when category clearly needs a new list that does not exist.
- otherwise false and use To Do as fallback.
"""


class TrelloCaptureError(Exception):
    """Raised when Trello capture routing fails."""


def _contains_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(re.search(rf"\b{re.escape(word)}\b", lower) for word in keywords)


def _fallback_create(decision: CaptureDecision, reason: str) -> CaptureDecision:
    return CaptureDecision(
        input_type=decision.input_type if decision.input_type != "completed" else "new_task",
        action="create_card",
        reason=f"{reason}. Created new card in To Do instead.",
        match_confidence="none",
        matched_card_id=None,
        matched_card_name=None,
        list_name=DEFAULT_LIST,
        create_list_if_missing=False,
        title=decision.title or decision.matched_card_name or "Untitled",
        notes=decision.notes,
        comment=None,
        due_date=decision.due_date,
        calendar_date=decision.calendar_date,
        calendar_end_date=decision.calendar_end_date,
    )


def enforce_safety(decision: CaptureDecision, user_text: str) -> CaptureDecision:
    if decision.match_confidence != "high" and decision.action in {
        "update_card",
        "comment_card",
        "move_to_done",
        "archive_card",
    }:
        return _fallback_create(decision, "Uncertain card match")

    if decision.action == "move_to_done":
        if not _contains_keyword(user_text, DONE_KEYWORDS):
            return _fallback_create(decision, "No clear completion keyword")

    if decision.action == "archive_card":
        if not _contains_keyword(user_text, ARCHIVE_KEYWORDS):
            if _contains_keyword(user_text, DONE_KEYWORDS):
                decision = decision.model_copy(update={"action": "move_to_done"})
            else:
                return _fallback_create(decision, "Archive not clearly requested")

    if decision.action in {"update_card", "comment_card"} and not decision.matched_card_id:
        return _fallback_create(decision, "Missing matched card")

    if decision.action == "move_to_done" and not decision.matched_card_id:
        return _fallback_create(decision, "Missing matched card for completion")

    if decision.action == "archive_card" and not decision.matched_card_id:
        return _fallback_create(decision, "Missing matched card for archive")

    return decision


def _resolve_target_list(snapshot: dict, decision: CaptureDecision) -> str:
    list_name = decision.list_name or DEFAULT_LIST
    try:
        return resolve_list_id_or_create(
            snapshot,
            list_name,
            allow_create=decision.create_list_if_missing,
        )
    except TrelloError:
        fallback = find_list_id(snapshot, DEFAULT_LIST)
        if fallback:
            logger.warning("List %s not found; falling back to To Do", list_name)
            return fallback
        raise


def _maybe_calendar(decision: CaptureDecision, result: CaptureResult) -> None:
    if not decision.calendar_date or not decision.title:
        return
    try:
        event_id = create_calendar_event(
            title=decision.title,
            date=decision.calendar_date,
            end_date=decision.calendar_end_date,
        )
        result.actions.append("create_calendar_event")
        result.log_lines.append(
            f"create_calendar_event title={decision.title!r} event_id={event_id!r}"
        )
    except GoogleCalendarError as exc:
        logger.exception("calendar create failed during capture")
        result.log_lines.append(f"calendar_error: {exc}")


def execute_decision(decision: CaptureDecision, snapshot: dict) -> CaptureResult:
    result = CaptureResult()

    logger.info(
        "trello capture action=%s input_type=%s list=%s matched_card=%s confidence=%s reason=%s",
        decision.action,
        decision.input_type,
        decision.list_name,
        decision.matched_card_id,
        decision.match_confidence,
        decision.reason,
    )

    if decision.action == "create_card":
        if not decision.title:
            raise TrelloCaptureError("create_card requires title")
        list_id = _resolve_target_list(snapshot, decision)
        card_id = create_card(
            title=decision.title,
            notes=decision.notes,
            due_date=decision.due_date,
            list_id=list_id,
        )
        result.actions.append("create_trello_card")
        result.log_lines.append(
            f"create_card title={decision.title!r} list={decision.list_name!r} card_id={card_id!r}"
        )
        db.insert_trello_card(
            title=decision.title,
            notes=decision.notes,
            due_date=decision.due_date,
            trello_card_id=card_id,
        )

    elif decision.action == "update_card":
        assert decision.matched_card_id
        update_card(
            decision.matched_card_id,
            name=decision.title,
            desc=decision.notes,
            due_date=decision.due_date,
        )
        result.actions.append("update_trello_card")
        result.log_lines.append(
            f"update_card card_id={decision.matched_card_id!r} name={decision.matched_card_name!r}"
        )

    elif decision.action == "comment_card":
        assert decision.matched_card_id
        comment = decision.comment or decision.notes or decision.title or ""
        add_comment(decision.matched_card_id, comment)
        result.actions.append("comment_trello_card")
        result.log_lines.append(
            f"comment_card card_id={decision.matched_card_id!r} comment={comment!r}"
        )

    elif decision.action == "move_to_done":
        assert decision.matched_card_id
        done_list_id = find_list_id(snapshot, DONE_LIST)
        if not done_list_id:
            raise TrelloCaptureError(f"Done list not found on board")
        move_card(decision.matched_card_id, done_list_id)
        result.actions.append("move_trello_done")
        result.log_lines.append(
            f"move_to_done card_id={decision.matched_card_id!r} list={DONE_LIST!r}"
        )

    elif decision.action == "archive_card":
        assert decision.matched_card_id
        archive_card(decision.matched_card_id)
        result.actions.append("archive_trello_card")
        result.log_lines.append(
            f"archive_card card_id={decision.matched_card_id!r} name={decision.matched_card_name!r}"
        )

    if decision.due_date and decision.matched_card_id and decision.action != "create_card":
        update_card(decision.matched_card_id, due_date=decision.due_date)
        result.log_lines.append(
            f"set_due card_id={decision.matched_card_id!r} due_date={decision.due_date!r}"
        )

    _maybe_calendar(decision, result)
    return result


def route_capture(settings: Settings, user_text: str) -> list[str]:
    snapshot = fetch_board_snapshot()
    client = Groq(api_key=settings.groq_api_key)

    payload = {
        "input": user_text.strip(),
        "board": snapshot,
    }
    prompt = ROUTING_PROMPT.format(today=date.today().isoformat())

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
            ],
        )
    except GroqAPIError as exc:
        logger.exception("Trello capture Groq API request failed")
        raise TrelloCaptureError("Capture routing unavailable") from exc

    raw = completion.choices[0].message.content
    if not raw:
        raise TrelloCaptureError("Empty routing response")

    try:
        decision = CaptureDecision.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Invalid capture routing payload: %s", raw)
        raise TrelloCaptureError("Invalid routing output") from exc

    decision = enforce_safety(decision, user_text)
    result = execute_decision(decision, snapshot)

    for line in result.log_lines:
        logger.info("trello capture result: %s", line)

    return result.actions
