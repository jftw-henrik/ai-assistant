from pydantic import BaseModel


class Todo(BaseModel):
    id: int
    title: str
    notes: str | None = None
    due_date: str | None = None
    google_task_id: str | None = None
    created_at: str


class Idea(BaseModel):
    id: int
    title: str
    description: str | None = None
    created_at: str


class Project(BaseModel):
    id: int
    title: str
    description: str | None = None
    created_at: str


class CalendarEvent(BaseModel):
    id: int
    title: str
    date: str
    created_at: str
