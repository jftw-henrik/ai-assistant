from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


SafeActionType = Literal[
    "create_card",
    "update_due_date",
    "add_labels",
    "create_calendar_event",
    "update_calendar_event",
]


class SafeAction(BaseModel):
    type: SafeActionType
    reason: str = ""
    card_id: str | None = None
    card_name: str | None = None
    list_name: str | None = None
    title: str | None = None
    notes: str | None = None
    due_date: str | None = None
    labels: list[str] = Field(default_factory=list)
    date: str | None = None
    end_date: str | None = None
    event_id: str | None = None


class AdvisoryAction(BaseModel):
    type: str
    card_id: str | None = None
    card_name: str | None = None
    suggested_list: str | None = None
    reason: str = ""


class BoardReviewResult(BaseModel):
    review_id: str
    summary_text: str
    findings: list[str] = Field(default_factory=list)
    safe_actions: list[SafeAction] = Field(default_factory=list)
    advisory_actions: list[AdvisoryAction] = Field(default_factory=list)


class ApplySafeRequest(BaseModel):
    review_id: str | None = None


class ApplySafeResult(BaseModel):
    review_id: str
    applied: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    def to_plain_text(self) -> str:
        lines = [f"Trello apply-safe (review {self.review_id})", ""]
        if self.applied:
            lines.append("Applied:")
            lines.extend(f"  ✅ {item}" for item in self.applied)
            lines.append("")
        if self.skipped:
            lines.append("Skipped:")
            lines.extend(f"  ⏭ {item}" for item in self.skipped)
            lines.append("")
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  ❌ {item}" for item in self.errors)
            lines.append("")
        if not self.applied and not self.errors:
            lines.append("No safe actions to apply.")
        return "\n".join(lines).strip()


def parse_review_payload(payload: dict[str, Any]) -> tuple[list[str], list[SafeAction], list[AdvisoryAction]]:
    findings = [str(item) for item in payload.get("findings", [])]
    safe_actions: list[SafeAction] = []
    for item in payload.get("safe_actions", []):
        try:
            safe_actions.append(SafeAction.model_validate(item))
        except ValidationError:
            continue
    advisory_actions = [
        AdvisoryAction.model_validate(item) for item in payload.get("advisory_only", [])
    ]
    return findings, safe_actions, advisory_actions
