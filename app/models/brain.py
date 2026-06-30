from typing import Any, Literal

from pydantic import BaseModel, Field

Intent = Literal[
    "task",
    "idea",
    "project",
    "meeting",
    "deadline",
    "update",
    "complete",
    "note",
]

Area = Literal[
    "work",
    "company",
    "home",
    "personal",
    "music",
    "finance",
    "admin",
]

PriorityLevel = Literal["low", "medium", "high", "critical"]

TargetSystem = Literal["trello", "calendar", "memory"]

SuggestedAction = Literal[
    "create",
    "update",
    "complete",
    "archive",
    "ask_clarification",
]


class TrelloListItem(BaseModel):
    id: str
    name: str


class TrelloCardItem(BaseModel):
    id: str
    name: str
    list_id: str | None = None
    list_name: str | None = None
    due: str | None = None
    desc: str | None = None
    labels: list[str] = Field(default_factory=list)


class CalendarEventItem(BaseModel):
    title: str
    start: str | None = None
    end: str | None = None


class UserProfile(BaseModel):
    name: str | None = None
    timezone: str | None = None
    notes: str | None = None


class BrainContext(BaseModel):
    trello_lists: list[TrelloListItem] = Field(default_factory=list)
    trello_cards: list[TrelloCardItem] = Field(default_factory=list)
    calendar_events_today: list[CalendarEventItem] = Field(default_factory=list)
    user_profile: UserProfile | None = None
    project_graph_summary: dict[str, Any] | None = None
    project_resolution: dict[str, Any] | None = None


class BrainDecision(BaseModel):
    intent: Intent
    title: str
    summary: str = ""
    project: str | None = None
    area: Area = "personal"
    urgency: PriorityLevel = "medium"
    importance: PriorityLevel = "medium"
    has_deadline: bool = False
    deadline_datetime: str | None = None
    target_systems: list[TargetSystem] = Field(default_factory=list)
    suggested_action: SuggestedAction = "create"
    matched_card_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    reasoning: str = ""
