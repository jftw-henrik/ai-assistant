from typing import Any

from app.db import repository as db
from app.integrations.google_calendar import GoogleCalendarError, create_calendar_event
from app.integrations.google_tasks import GoogleTasksError, create_task
from app.integrations.trello import TrelloError, create_card
from app.tools.base import Tool


class CreateCalendarEventTool(Tool):
    @property
    def name(self) -> str:
        return "create_calendar_event"

    @property
    def description(self) -> str:
        return (
            "Create a calendar event for meetings, appointments, interviews, "
            "or any activity with a specific date and/or time."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Event title"},
                "date": {
                    "type": "string",
                    "description": "ISO 8601 start datetime, e.g. 2026-07-03T14:00",
                },
                "end_date": {
                    "type": "string",
                    "description": "Optional ISO 8601 end datetime. Defaults to 1 hour after start.",
                },
            },
            "required": ["title", "date"],
        }

    def execute(self, **kwargs: Any) -> None:
        title = kwargs["title"]
        date = kwargs["date"]
        end_date = kwargs.get("end_date")

        try:
            event_id = create_calendar_event(
                title=title,
                date=date,
                end_date=end_date,
            )
        except GoogleCalendarError as exc:
            raise RuntimeError(str(exc)) from exc

        print(
            "create_calendar_event("
            f"title={title!r}, date={date!r}, event_id={event_id!r})"
        )
        db.insert_calendar_event(title=title, date=date)


class CreateTrelloCardTool(Tool):
    @property
    def name(self) -> str:
        return "create_trello_card"

    @property
    def description(self) -> str:
        return (
            "Create a Trello card in the default list. Main store for tasks, ideas, "
            "and projects. Also use alongside create_calendar_event when a date is present."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Card title"},
                "notes": {
                    "type": "string",
                    "description": "Optional description or context",
                },
                "due_date": {
                    "type": "string",
                    "description": "Optional due date as ISO 8601 date or datetime",
                },
            },
            "required": ["title"],
        }

    def execute(self, **kwargs: Any) -> None:
        title = kwargs["title"]
        notes = kwargs.get("notes")
        due_date = kwargs.get("due_date")

        try:
            card_id = create_card(title=title, notes=notes, due_date=due_date)
        except TrelloError as exc:
            raise RuntimeError(str(exc)) from exc

        parts = [f"title={title!r}", f"card_id={card_id!r}"]
        if notes:
            parts.append(f"notes={notes!r}")
        if due_date:
            parts.append(f"due_date={due_date!r}")
        print(f"create_trello_card({', '.join(parts)})")
        db.insert_trello_card(
            title=title,
            notes=notes,
            due_date=due_date,
            trello_card_id=card_id,
        )


class CreateTodoTool(Tool):
    @property
    def name(self) -> str:
        return "create_todo"

    @property
    def description(self) -> str:
        return (
            "Legacy: create a Google Tasks item. Prefer create_trello_card when Trello "
            "is available. Only use for explicit Google Tasks requests or when Trello "
            "is unavailable."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Task title"},
                "notes": {
                    "type": "string",
                    "description": "Optional extra context or details",
                },
                "due_date": {
                    "type": "string",
                    "description": "Optional due date as ISO 8601 date or datetime, e.g. 2026-07-03",
                },
            },
            "required": ["title"],
        }

    def execute(self, **kwargs: Any) -> None:
        title = kwargs["title"]
        notes = kwargs.get("notes")
        due_date = kwargs.get("due_date")

        try:
            task_id = create_task(title=title, notes=notes, due_date=due_date)
        except GoogleTasksError as exc:
            raise RuntimeError(str(exc)) from exc

        parts = [f"title={title!r}", f"task_id={task_id!r}"]
        if notes:
            parts.append(f"notes={notes!r}")
        if due_date:
            parts.append(f"due_date={due_date!r}")
        print(f"create_todo({', '.join(parts)})")
        db.insert_todo(
            title=title,
            notes=notes,
            due_date=due_date,
            google_task_id=task_id,
        )


class SaveIdeaTool(Tool):
    @property
    def name(self) -> str:
        return "save_idea"

    @property
    def description(self) -> str:
        return (
            "Save an idea, note, brainstorm, or concept that is not yet "
            "a task or project."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Idea title"},
                "description": {
                    "type": "string",
                    "description": "Optional extra context",
                },
            },
            "required": ["title"],
        }

    def execute(self, **kwargs: Any) -> None:
        title = kwargs["title"]
        description = kwargs.get("description")
        parts = [f"title={title!r}"]
        if description:
            parts.append(f"description={description!r}")
        print(f"save_idea({', '.join(parts)})")
        db.insert_idea(title=title, description=description)


class CreateProjectTool(Tool):
    @property
    def name(self) -> str:
        return "create_project"

    @property
    def description(self) -> str:
        return (
            "Create a project for a multi-step initiative or named undertaking "
            "with broader scope than a single task."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Project title"},
                "description": {
                    "type": "string",
                    "description": "Optional project summary",
                },
            },
            "required": ["title"],
        }

    def execute(self, **kwargs: Any) -> None:
        title = kwargs["title"]
        description = kwargs.get("description")
        parts = [f"title={title!r}"]
        if description:
            parts.append(f"description={description!r}")
        print(f"create_project({', '.join(parts)})")
        db.insert_project(title=title, description=description)
