from pydantic import BaseModel, Field


class CaptureRequest(BaseModel):
    text: str = Field(..., min_length=1, examples=["Interview Friday at 14 with NZM"])
