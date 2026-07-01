from pydantic import BaseModel, Field


class CalendarSyncEventResult(BaseModel):
    event_id: str
    title: str
    outcome: str
    reasoning: str = ""
    trello_card_id: str | None = None


class CalendarSyncResult(BaseModel):
    total: int = 0
    created: int = 0
    existed: int = 0
    updated: int = 0
    skipped: int = 0
    events: list[CalendarSyncEventResult] = Field(default_factory=list)

    def to_plain_text(self) -> str:
        return (
            f"Synced {self.total} calendar events: "
            f"{self.created} created, {self.existed} already existed, "
            f"{self.skipped} skipped."
            + (f" {self.updated} updated." if self.updated else "")
        )
