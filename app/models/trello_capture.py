from typing import Literal

from pydantic import BaseModel, Field

InputType = Literal[
    "new_task",
    "idea",
    "project",
    "update",
    "completed",
    "deadline",
]

CaptureAction = Literal[
    "create_card",
    "update_card",
    "comment_card",
    "move_to_done",
    "archive_card",
]

MatchConfidence = Literal["high", "low", "none"]


class CaptureDecision(BaseModel):
    input_type: InputType
    action: CaptureAction
    reason: str = ""
    match_confidence: MatchConfidence = "none"
    matched_card_id: str | None = None
    matched_card_name: str | None = None
    list_name: str = "To Do"
    create_list_if_missing: bool = False
    title: str | None = None
    notes: str | None = None
    comment: str | None = None
    due_date: str | None = None
    calendar_date: str | None = None
    calendar_end_date: str | None = None


class CaptureResult(BaseModel):
    actions: list[str] = Field(default_factory=list)
    log_lines: list[str] = Field(default_factory=list)
