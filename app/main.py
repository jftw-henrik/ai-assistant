import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError

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


def _capture_error(message: str) -> PlainTextResponse:
    return PlainTextResponse(
        f"❌ Error: {message}",
        media_type=CAPTURE_MEDIA_TYPE,
        status_code=200,
    )


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
    version="0.4.1",
    lifespan=lifespan,
)


@app.get("/health", response_class=PlainTextResponse)
async def health() -> PlainTextResponse:
    return PlainTextResponse("OK", media_type=CAPTURE_MEDIA_TYPE)


@app.post("/capture", response_class=PlainTextResponse)
async def capture(
    request: Request,
    agent: AgentService = Depends(get_agent),
) -> PlainTextResponse:
    logger.info("capture request headers: %s", dict(request.headers))

    try:
        raw_body = await request.body()
        raw_text = raw_body.decode("utf-8", errors="replace")
        logger.info("capture raw body: %s", raw_text)

        try:
            payload = json.loads(raw_body)
            body = CaptureRequest.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.exception("capture invalid request body")
            return _capture_error("Invalid request body")

        text = body.text.strip()
        logger.info("capture parsed text: %s", text)

        tool_name = agent.run(text)
        logger.info("capture chosen tool: %s", tool_name)

        return PlainTextResponse(
            confirmation_for_tool(tool_name),
            media_type=CAPTURE_MEDIA_TYPE,
            status_code=200,
        )
    except AgentError as exc:
        logger.exception("capture agent error")
        return _capture_error(str(exc))
    except Exception as exc:
        logger.exception("capture unexpected error")
        return _capture_error(str(exc))


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
