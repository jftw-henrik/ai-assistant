import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings
from app.db import repository as db
from app.integrations.google_calendar import (
    GoogleCalendarError,
    is_google_calendar_available,
    list_upcoming_events,
)
from app.integrations.sync_metadata import (
    append_gcal_metadata,
    extract_gcal_event_id,
    gcal_source_marker,
)
from app.integrations.trello import (
    TrelloError,
    create_card,
    fetch_board_snapshot,
    find_list_id,
    is_trello_available,
    update_card,
)
from app.models.brain import CalendarEventItem, UserProfile
from app.models.calendar_sync import CalendarSyncEventResult, CalendarSyncResult
from app.models.project_graph import ProjectGraph
from app.services.brain import BrainError, analyze_input
from app.services.project_graph import (
    ProjectGraphError,
    build_graph_from_trello,
    enrich_graph_with_semantic_projects,
    resolve_project_for_input,
)
from app.services.trello_capture import (
    AREA_TO_LIST,
    DEFAULT_LIST,
    build_brain_context,
    brain_to_capture_decision,
)

logger = logging.getLogger(__name__)

ACTIONABLE_KEYWORDS = (
    "meeting",
    "interview",
    "call",
    "appointment",
    "deadline",
    "möte",
    "samtal",
    "intervju",
    "ring",
    "besök",
    "launch",
    "release",
)


class CalendarTrelloSyncError(Exception):
    """Raised when calendar-to-Trello sync fails."""


def _find_card_by_gcal_id(snapshot: dict[str, Any], event_id: str) -> dict[str, Any] | None:
    marker = gcal_source_marker(event_id)
    for card in snapshot.get("cards", []):
        if marker in (card.get("desc") or ""):
            return card
        if extract_gcal_event_id(card.get("desc")) == event_id:
            return card
    return None


def _is_clearly_actionable(event: dict[str, Any]) -> bool:
    title = (event.get("title") or "").lower()
    if any(keyword in title for keyword in ACTIONABLE_KEYWORDS):
        return True
    if event.get("location"):
        return True
    description = (event.get("description") or "").strip()
    return len(description) > 10


def _should_skip_event(event: dict[str, Any]) -> tuple[bool, str]:
    if event.get("status") == "cancelled":
        return True, "cancelled event"

    title = (event.get("title") or "").strip()
    if not title or title == "(No title)":
        return True, "empty or missing title"

    if event.get("visibility") == "private" and not _is_clearly_actionable(event):
        return True, "private event without clear action"

    return False, ""


def _event_input_text(event: dict[str, Any]) -> str:
    title = event.get("title", "").strip()
    start = event.get("start", "")
    location = event.get("location", "")
    parts = [f"Calendar event: {title}"]
    if start:
        parts.append(f"on {start}")
    if location:
        parts.append(f"at {location}")
    description = (event.get("description") or "").strip()
    if description:
        parts.append(description[:200])
    return " ".join(parts)


def _due_datetime_for_event(event: dict[str, Any], timezone: str) -> str | None:
    start = event.get("start")
    if not start:
        return None
    if event.get("all_day"):
        return start
    parsed = datetime.fromisoformat(start.replace("Z", "+00:00"))
    local = parsed.astimezone(ZoneInfo(timezone))
    return local.isoformat()


def _classify_event(
    settings: Settings,
    event: dict[str, Any],
    snapshot: dict[str, Any],
    project_graph: ProjectGraph | None,
    calendar_events: list[CalendarEventItem],
) -> tuple[str, str, str, str | None]:
    """Return list_name, title, reasoning, matched_card_id using Brain + ProjectGraph."""
    event_text = _event_input_text(event)
    project_resolution = None

    if project_graph:
        try:
            project_resolution = resolve_project_for_input(event_text, project_graph)
        except ProjectGraphError as exc:
            logger.warning("project resolution failed for event %s: %s", event.get("id"), exc)

    context = build_brain_context(
        snapshot,
        calendar_events,
        user_profile=UserProfile(timezone=settings.google_calendar_timezone),
        project_graph=project_graph,
        project_resolution=project_resolution,
    )

    try:
        brain = analyze_input(event_text, context)
        capture = brain_to_capture_decision(
            brain,
            snapshot,
            project_resolution=project_resolution,
        )
        list_name = capture.list_name or DEFAULT_LIST
        title = capture.title or event.get("title", "Untitled event")
        reasoning = (
            f"brain intent={brain.intent} area={brain.area} "
            f"project={brain.project or project_resolution.project_name if project_resolution else None}; "
            f"{brain.reasoning}"
        )
        return list_name, title, reasoning, capture.matched_card_id
    except BrainError as exc:
        logger.warning("brain classification failed for event %s: %s", event.get("id"), exc)
        list_name = DEFAULT_LIST
        if project_resolution and project_resolution.target_list:
            list_name = project_resolution.target_list
        elif project_resolution and project_resolution.area:
            list_name = AREA_TO_LIST.get(project_resolution.area, DEFAULT_LIST)
        return list_name, event.get("title", "Untitled event"), f"brain fallback: {exc}", None


def _build_project_graph(snapshot: dict[str, Any]) -> ProjectGraph | None:
    try:
        graph = build_graph_from_trello(snapshot)
        return enrich_graph_with_semantic_projects(graph)
    except ProjectGraphError as exc:
        logger.warning("project graph unavailable for calendar sync: %s", exc)
        return None
    except Exception as exc:
        logger.warning("project graph error for calendar sync: %s", exc, exc_info=True)
        return None


def sync_calendar_to_trello(settings: Settings, *, days: int = 30) -> CalendarSyncResult:
    if not is_google_calendar_available():
        raise CalendarTrelloSyncError("Google Calendar is not configured")
    if not is_trello_available():
        raise CalendarTrelloSyncError("Trello is not configured")

    try:
        events = list_upcoming_events(days=days)
    except GoogleCalendarError as exc:
        raise CalendarTrelloSyncError(str(exc)) from exc

    snapshot = fetch_board_snapshot()
    project_graph = _build_project_graph(snapshot)
    calendar_context = [
        CalendarEventItem(
            title=event["title"],
            start=event.get("start"),
            end=event.get("end"),
        )
        for event in events
    ]

    result = CalendarSyncResult(total=len(events))

    for event in events:
        event_id = event.get("id")
        if not event_id:
            result.skipped += 1
            result.events.append(
                CalendarSyncEventResult(
                    event_id="unknown",
                    title=event.get("title", ""),
                    outcome="skipped",
                    reasoning="missing event id",
                )
            )
            continue

        skip, skip_reason = _should_skip_event(event)
        if skip:
            result.skipped += 1
            entry = CalendarSyncEventResult(
                event_id=event_id,
                title=event.get("title", ""),
                outcome="skipped",
                reasoning=skip_reason,
            )
            result.events.append(entry)
            logger.info(
                "calendar sync skipped event_id=%s title=%r reason=%s",
                event_id,
                event.get("title"),
                skip_reason,
            )
            continue

        existing = _find_card_by_gcal_id(snapshot, event_id)
        due_date = _due_datetime_for_event(event, settings.google_calendar_timezone)

        if existing:
            result.existed += 1
            reasoning = "matched existing Trello card by google-calendar source metadata"
            if due_date and existing.get("due") != due_date:
                try:
                    update_card(existing["id"], due_date=due_date)
                    result.updated += 1
                    reasoning += "; updated due date"
                except TrelloError as exc:
                    reasoning += f"; due update failed: {exc}"
            entry = CalendarSyncEventResult(
                event_id=event_id,
                title=event.get("title", ""),
                outcome="existed",
                reasoning=reasoning,
                trello_card_id=existing["id"],
            )
            result.events.append(entry)
            logger.info(
                "calendar sync existed event_id=%s card_id=%s reasoning=%s",
                event_id,
                existing["id"],
                reasoning,
            )
            continue

        list_name, title, reasoning, matched_card_id = _classify_event(
            settings,
            event,
            snapshot,
            project_graph,
            calendar_context,
        )

        if matched_card_id:
            matched = next(
                (card for card in snapshot.get("cards", []) if card["id"] == matched_card_id),
                None,
            )
            if matched and not extract_gcal_event_id(matched.get("desc")):
                notes = append_gcal_metadata(
                    matched.get("desc"),
                    event_id=event_id,
                    html_link=event.get("html_link"),
                )
                try:
                    update_card(
                        matched_card_id,
                        desc=notes,
                        due_date=due_date,
                    )
                    result.existed += 1
                    result.updated += 1
                    matched["desc"] = notes
                    entry = CalendarSyncEventResult(
                        event_id=event_id,
                        title=matched.get("name", title),
                        outcome="existed",
                        reasoning=f"{reasoning}; linked existing card by brain match",
                        trello_card_id=matched_card_id,
                    )
                    result.events.append(entry)
                    logger.info(
                        "calendar sync linked existing event_id=%s card_id=%s reasoning=%s",
                        event_id,
                        matched_card_id,
                        entry.reasoning,
                    )
                    continue
                except TrelloError as exc:
                    logger.warning(
                        "calendar sync link existing failed event_id=%s card_id=%s: %s",
                        event_id,
                        matched_card_id,
                        exc,
                    )

        list_id = find_list_id(snapshot, list_name) or find_list_id(snapshot, DEFAULT_LIST)
        if not list_id:
            result.skipped += 1
            entry = CalendarSyncEventResult(
                event_id=event_id,
                title=event.get("title", ""),
                outcome="skipped",
                reasoning=f"target list not found: {list_name}",
            )
            result.events.append(entry)
            logger.info(
                "calendar sync skipped event_id=%s title=%r reason=%s",
                event_id,
                event.get("title"),
                entry.reasoning,
            )
            continue

        notes = append_gcal_metadata(
            event.get("description"),
            event_id=event_id,
            html_link=event.get("html_link"),
        )

        try:
            card_id = create_card(
                title=title,
                notes=notes,
                due_date=due_date,
                list_id=list_id,
            )
        except TrelloError as exc:
            result.skipped += 1
            entry = CalendarSyncEventResult(
                event_id=event_id,
                title=event.get("title", ""),
                outcome="skipped",
                reasoning=f"trello create failed: {exc}",
            )
            result.events.append(entry)
            logger.warning(
                "calendar sync create failed event_id=%s title=%r error=%s",
                event_id,
                event.get("title"),
                exc,
            )
            continue

        result.created += 1
        snapshot["cards"].append(
            {
                "id": card_id,
                "name": title,
                "desc": notes,
                "due": due_date,
                "list_id": list_id,
                "list_name": list_name,
                "labels": [],
            }
        )
        db.insert_trello_card(
            title=title,
            notes=notes,
            due_date=due_date,
            trello_card_id=card_id,
        )
        entry = CalendarSyncEventResult(
            event_id=event_id,
            title=title,
            outcome="created",
            reasoning=f"{reasoning}; list={list_name}",
            trello_card_id=card_id,
        )
        result.events.append(entry)
        logger.info(
            "calendar sync created event_id=%s card_id=%s list=%s reasoning=%s",
            event_id,
            card_id,
            list_name,
            reasoning,
        )

    logger.info(
        "calendar sync complete total=%d created=%d existed=%d updated=%d skipped=%d",
        result.total,
        result.created,
        result.existed,
        result.updated,
        result.skipped,
    )
    return result
