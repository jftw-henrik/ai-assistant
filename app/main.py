import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse

from app.config import Settings, get_settings
from app.db import (
    init_db,
    list_calendar_events,
    list_ideas,
    list_projects,
    list_todos,
)
from app.models.capture import CaptureRequest
from app.models.records import CalendarEvent, Idea, Project, Todo
from app.services.agent import AgentError, AgentService
from app.services.confirmations import confirmation_for_tool

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

CAPTURE_MEDIA_TYPE = "text/plain; charset=utf-8"


def get_agent(settings: Settings = Depends(get_settings)) -> AgentService:
    return AgentService(settings)


def run_capture(text: str, agent: AgentService) -> str:
    try:
        tool_name = agent.run(text)
    except AgentError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    return confirmation_for_tool(tool_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fail fast if GROQ_API_KEY is missing
    init_db()
    logger.info("Henrik Assistant starting")
    yield
    logger.info("Henrik Assistant shutting down")


app = FastAPI(
    title="Henrik Assistant",
    description="AI agent that decides which tool to use for captured text.",
    version="0.4.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/capture",
    response_class=PlainTextResponse,
    responses={502: {"description": "Agent service error"}},
)
async def capture(
    body: CaptureRequest,
    agent: AgentService = Depends(get_agent),
) -> PlainTextResponse:
    return PlainTextResponse(run_capture(body.text, agent), media_type=CAPTURE_MEDIA_TYPE)


@app.get("/todos", response_model=list[Todo])
async def get_todos() -> list[Todo]:
    return list_todos()


@app.get("/ideas", response_model=list[Idea])
async def get_ideas() -> list[Idea]:
    return list_ideas()


@app.get("/projects", response_model=list[Project])
async def get_projects() -> list[Project]:
    return list_projects()


@app.get("/calendar-events", response_model=list[CalendarEvent])
async def get_calendar_events() -> list[CalendarEvent]:
    return list_calendar_events()
