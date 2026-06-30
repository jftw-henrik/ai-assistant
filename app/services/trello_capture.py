import json
import logging
import re
from datetime import date
from typing import Any

from groq import APIError as GroqAPIError
from groq import Groq

from app.config import Settings
from app.integrations.google_calendar import (
    GoogleCalendarError,
    create_calendar_event,
    is_google_calendar_available,
    list_today_events,
)
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
from app.models.brain import (
    BrainContext,
    BrainDecision,
    CalendarEventItem,
    SuggestedAction,
    TrelloCardItem,
    TrelloListItem,
    UserProfile,
)
from app.models.capture_result import CaptureBatchResult, CaptureItemResult
from app.models.project_graph import ProjectGraph, ProjectResolution
from app.models.trello_capture import (
    CaptureAction,
    CaptureDecision,
    CaptureResult,
    InputType,
    MatchConfidence,
)
from app.services.brain import BrainError, analyze_input
from app.services.input_splitter import split_capture_input
from app.services.project_graph import (
    ProjectGraphError,
    build_graph_from_trello,
    enrich_graph_with_semantic_projects,
    resolve_project_for_input,
)

logger = logging.getLogger(__name__)

DONE_KEYWORDS = ("done", "klart", "fixed", "completed", "finished", "färdig", "klar")
ARCHIVE_KEYWORDS = ("archive", "archived", "ta bort", "rensa")
DEFAULT_LIST = "To Do"
DONE_LIST = "Done"
HIGH_CONFIDENCE = 0.8

AREA_TO_LIST: dict[str, str] = {
    "work": "Work",
    "music": "Work",
    "company": "FIRMOR",
    "finance": "FIRMOR",
    "admin": "FIRMOR",
    "home": "To Do",
    "personal": "To Do",
}

INTENT_TO_INPUT_TYPE: dict[str, InputType] = {
    "task": "new_task",
    "idea": "idea",
    "project": "project",
    "meeting": "deadline",
    "deadline": "deadline",
    "update": "update",
    "complete": "completed",
    "note": "new_task",
}

ACTION_MAP: dict[SuggestedAction, CaptureAction] = {
    "create": "create_card",
    "update": "update_card",
    "complete": "move_to_done",
    "archive": "archive_card",
    "ask_clarification": "create_card",
}

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


def _fetch_calendar_events_safe() -> list[CalendarEventItem]:
    if not is_google_calendar_available():
        return []
    try:
        return [
            CalendarEventItem(title=event["title"], start=event.get("start"), end=event.get("end"))
            for event in list_today_events()
        ]
    except GoogleCalendarError:
        logger.warning("calendar fetch failed for brain context")
        return []


def build_brain_context(
    snapshot: dict[str, Any],
    calendar_events: list[CalendarEventItem],
    *,
    user_profile: UserProfile | None = None,
    project_graph: ProjectGraph | None = None,
    project_resolution: ProjectResolution | None = None,
) -> BrainContext:
    return BrainContext(
        trello_lists=[
            TrelloListItem(id=item["id"], name=item["name"]) for item in snapshot["lists"]
        ],
        trello_cards=[
            TrelloCardItem(
                id=card["id"],
                name=card["name"],
                list_id=card.get("list_id"),
                list_name=card.get("list_name"),
                due=card.get("due"),
                desc=card.get("desc"),
                labels=card.get("labels", []),
            )
            for card in snapshot["cards"]
        ],
        calendar_events_today=calendar_events,
        user_profile=user_profile,
        project_graph_summary=project_graph.to_summary() if project_graph else None,
        project_resolution=project_resolution.model_dump(mode="json") if project_resolution else None,
    )


def _card_name_for_id(snapshot: dict[str, Any], card_id: str | None) -> str | None:
    if not card_id:
        return None
    for card in snapshot["cards"]:
        if card["id"] == card_id:
            return card["name"]
    return None


def _confidence_to_match(confidence: float) -> MatchConfidence:
    if confidence >= HIGH_CONFIDENCE:
        return "high"
    if confidence >= 0.5:
        return "low"
    return "none"


def brain_to_capture_decision(
    brain: BrainDecision,
    snapshot: dict[str, Any],
    *,
    project_resolution: ProjectResolution | None = None,
) -> CaptureDecision:
    match_confidence = _confidence_to_match(brain.confidence)
    matched_card_id = brain.matched_card_id if match_confidence == "high" else None
    matched_card_name = _card_name_for_id(snapshot, matched_card_id)

    if project_resolution:
        if (
            project_resolution.suggested_action == "update_existing"
            and project_resolution.matched_card_id
            and project_resolution.confidence >= HIGH_CONFIDENCE
        ):
            matched_card_id = project_resolution.matched_card_id
            matched_card_name = _card_name_for_id(snapshot, matched_card_id)
            match_confidence = "high"

    action = ACTION_MAP[brain.suggested_action]

    if project_resolution and project_resolution.suggested_action == "update_existing" and matched_card_id:
        action = "update_card"

    if brain.suggested_action == "update" and not matched_card_id:
        action = "create_card"
        match_confidence = "none"

    if brain.suggested_action in {"complete", "archive"} and not matched_card_id:
        action = "create_card"
        match_confidence = "none"

    project_name = brain.project
    list_name = AREA_TO_LIST.get(brain.area, DEFAULT_LIST)

    if project_resolution:
        if project_resolution.project_name:
            project_name = project_resolution.project_name
        if project_resolution.target_list:
            list_name = project_resolution.target_list

    notes = brain.summary or None
    if project_name:
        notes = f"{notes}\nProject: {project_name}".strip() if notes else f"Project: {project_name}"

    due_date = brain.deadline_datetime if brain.has_deadline else None
    calendar_date = None
    if "calendar" in brain.target_systems and brain.has_deadline and brain.deadline_datetime:
        calendar_date = brain.deadline_datetime
    if "calendar" in brain.target_systems and brain.intent == "meeting" and brain.deadline_datetime:
        calendar_date = brain.deadline_datetime

    return CaptureDecision(
        input_type=INTENT_TO_INPUT_TYPE.get(brain.intent, "new_task"),
        action=action,
        reason=brain.reasoning,
        match_confidence=match_confidence,
        matched_card_id=matched_card_id,
        matched_card_name=matched_card_name,
        list_name=list_name,
        create_list_if_missing=False,
        title=brain.title,
        notes=notes,
        comment=brain.summary or None,
        due_date=due_date,
        calendar_date=calendar_date,
        calendar_end_date=None,
    )


def _legacy_route_decision(
    settings: Settings,
    user_text: str,
    snapshot: dict[str, Any],
) -> CaptureDecision:
    client = Groq(api_key=settings.groq_api_key)
    payload = {
        "input": user_text.strip(),
        "board": snapshot,
    }
    prompt = ROUTING_PROMPT.format(today=date.today().isoformat())

    completion = client.chat.completions.create(
        model=settings.groq_model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
        ],
    )

    raw = completion.choices[0].message.content
    if not raw:
        raise TrelloCaptureError("Empty routing response")

    return CaptureDecision.model_validate(json.loads(raw))


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


def _build_project_graph(snapshot: dict[str, Any]) -> tuple[ProjectGraph | None, bool, str | None]:
    try:
        graph = build_graph_from_trello(snapshot)
        graph = enrich_graph_with_semantic_projects(graph)
        return graph, False, None
    except ProjectGraphError as exc:
        logger.warning("project graph failed, continuing without graph context: %s", exc)
        return None, True, str(exc)
    except Exception as exc:
        logger.warning(
            "project graph error, continuing without graph context: %s",
            exc,
            exc_info=True,
        )
        return None, True, str(exc)


def _route_single_item(
    settings: Settings,
    user_text: str,
    snapshot: dict[str, Any],
    calendar_events: list[CalendarEventItem],
    project_graph: ProjectGraph | None,
) -> CaptureItemResult:
    project_resolution: ProjectResolution | None = None

    if project_graph:
        try:
            project_resolution = resolve_project_for_input(user_text, project_graph)
            logger.info(
                "project graph item=%r matched_project=%r confidence=%.2f action=%s reasoning=%s",
                user_text,
                project_resolution.project_name,
                project_resolution.confidence,
                project_resolution.suggested_action,
                project_resolution.reasoning,
            )
        except ProjectGraphError as exc:
            logger.warning("project resolution failed for item %r: %s", user_text, exc)
        except Exception as exc:
            logger.warning(
                "project resolution error for item %r: %s",
                user_text,
                exc,
                exc_info=True,
            )

    context = build_brain_context(
        snapshot,
        calendar_events,
        user_profile=UserProfile(timezone=settings.google_calendar_timezone),
        project_graph=project_graph,
        project_resolution=project_resolution,
    )

    used_fallback = False
    fallback_reason: str | None = None
    brain_decision: BrainDecision | None = None
    intent: str | None = None

    try:
        brain_decision = analyze_input(user_text, context)
        intent = brain_decision.intent
        logger.info(
            "brain decision item=%r intent=%s action=%s area=%s confidence=%.2f title=%r",
            user_text,
            brain_decision.intent,
            brain_decision.suggested_action,
            brain_decision.area,
            brain_decision.confidence,
            brain_decision.title,
        )
        decision = brain_to_capture_decision(
            brain_decision,
            snapshot,
            project_resolution=project_resolution,
        )
    except BrainError as exc:
        used_fallback = True
        fallback_reason = str(exc)
        logger.warning("brain routing failed for item %r, using legacy fallback: %s", user_text, exc)
        try:
            decision = _legacy_route_decision(settings, user_text, snapshot)
            intent = decision.input_type
        except GroqAPIError as groq_exc:
            logger.exception("Trello capture Groq API request failed for item %r", user_text)
            raise TrelloCaptureError("Capture routing unavailable") from groq_exc
        except (json.JSONDecodeError, ValueError) as parse_exc:
            logger.error("Invalid legacy capture routing payload for item %r", user_text)
            raise TrelloCaptureError("Invalid routing output") from parse_exc
    except Exception as exc:
        used_fallback = True
        fallback_reason = str(exc)
        logger.warning(
            "brain routing error for item %r, using legacy fallback: %s",
            user_text,
            exc,
            exc_info=True,
        )
        try:
            decision = _legacy_route_decision(settings, user_text, snapshot)
            intent = decision.input_type
        except GroqAPIError as groq_exc:
            logger.exception("Trello capture Groq API request failed for item %r", user_text)
            raise TrelloCaptureError("Capture routing unavailable") from groq_exc
        except (json.JSONDecodeError, ValueError) as parse_exc:
            logger.error("Invalid legacy capture routing payload for item %r", user_text)
            raise TrelloCaptureError("Invalid routing output") from parse_exc

    logger.info(
        "capture item routing item=%r brain_fallback=%s brain_fallback_reason=%s",
        user_text,
        used_fallback,
        fallback_reason,
    )

    decision = enforce_safety(decision, user_text)
    result = execute_decision(decision, snapshot)

    title = decision.title or (brain_decision.title if brain_decision else user_text)
    logger.info(
        "capture item executed item=%r action=%s list=%s tools=%s",
        user_text,
        decision.action,
        decision.list_name,
        result.actions,
    )

    return CaptureItemResult(
        text=user_text,
        title=title,
        list_name=decision.list_name or DEFAULT_LIST,
        actions=result.actions,
        intent=intent,
    )


def route_capture(settings: Settings, user_text: str) -> CaptureBatchResult:
    item_texts = split_capture_input(user_text)
    if not item_texts:
        raise TrelloCaptureError("Empty capture text")

    snapshot = fetch_board_snapshot()
    calendar_events = _fetch_calendar_events_safe()
    project_graph, project_graph_fallback, project_graph_fallback_reason = _build_project_graph(snapshot)

    logger.info(
        "capture batch item_count=%d project_graph_fallback=%s project_graph_fallback_reason=%s",
        len(item_texts),
        project_graph_fallback,
        project_graph_fallback_reason,
    )

    items: list[CaptureItemResult] = []
    for item_text in item_texts:
        items.append(
            _route_single_item(
                settings,
                item_text,
                snapshot,
                calendar_events,
                project_graph,
            )
        )

    return CaptureBatchResult(items=items)
