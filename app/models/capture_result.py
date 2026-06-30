from pydantic import BaseModel, Field


class CaptureItemResult(BaseModel):
    text: str
    title: str
    list_name: str = "To Do"
    actions: list[str] = Field(default_factory=list)
    intent: str | None = None


class CaptureBatchResult(BaseModel):
    items: list[CaptureItemResult] = Field(default_factory=list)

    @property
    def all_actions(self) -> list[str]:
        actions: list[str] = []
        for item in self.items:
            actions.extend(item.actions)
        return actions
