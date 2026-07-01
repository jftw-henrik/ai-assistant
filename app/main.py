import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.db import (
    get_latest_trello_review,
    get_trello_review,
    init_db,
    list_calendar_events,
    list_ideas,
    list_projects,
    list_todos,
    save_trello_review,
)
from app.models.capture import CaptureRequest
from app.models.records import CalendarEvent, Idea, Project, Todo
from app.models.trello_review import ApplySafeRequest
from app.services.agent import AgentError, AgentService
from app.services.confirmations import confirmation_for_capture
from app.services.calendar_trello_sync import CalendarTrelloSyncError, sync_calendar_to_trello
from app.services.daily_briefing import DailyBriefingService
from app.services.sync_runner import SyncRunError, run_all_syncs
from app.services.trello_apply import TrelloApplyError, apply_safe_actions
from app.services.trello_review_agent import TrelloReviewAgent, TrelloReviewError

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

CAPTURE_MEDIA_TYPE = "text/plain; charset=utf-8"


def get_agent(settings: Settings = Depends(get_settings)) -> AgentService:
    return AgentService(settings)


def _plain_error(message: str) -> PlainTextResponse:
    return PlainTextResponse(
        f"❌ Error: {message}",
        media_type=CAPTURE_MEDIA_TYPE,
        status_code=200,
    )


def get_review_agent(settings: Settings = Depends(get_settings)) -> TrelloReviewAgent:
    return TrelloReviewAgent(settings)


def get_briefing_service(settings: Settings = Depends(get_settings)) -> DailyBriefingService:
    return DailyBriefingService(settings)


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
    version="0.5.0",
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
            return _plain_error("Invalid request body")

        text = body.text.strip()
        logger.info("capture parsed text: %s", text)

        batch = agent.run(text)
        logger.info("capture chosen tools: %s", batch.all_actions)

        return PlainTextResponse(
            confirmation_for_capture(batch),
            media_type=CAPTURE_MEDIA_TYPE,
            status_code=200,
        )
    except AgentError as exc:
        logger.exception("capture agent error")
        return _plain_error(str(exc))
    except Exception as exc:
        logger.exception("capture unexpected error")
        return _plain_error(str(exc))


@app.post("/sync/calendar-to-trello", response_class=PlainTextResponse)
async def sync_calendar_to_trello_endpoint(
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    try:
        result = sync_calendar_to_trello(settings)
        logger.info("calendar-to-trello sync: %s", result.to_plain_text())
        return PlainTextResponse(result.to_plain_text(), media_type=CAPTURE_MEDIA_TYPE)
    except CalendarTrelloSyncError as exc:
        logger.exception("calendar-to-trello sync failed")
        return _plain_error(str(exc))
    except Exception as exc:
        logger.exception("calendar-to-trello sync unexpected error")
        return _plain_error(str(exc))


@app.post("/sync/run-all", response_class=PlainTextResponse)
async def sync_run_all_endpoint(
    settings: Settings = Depends(get_settings),
) -> PlainTextResponse:
    try:
        summary = run_all_syncs(settings)
        logger.info("run-all sync: %s", summary.replace("\n", " | "))
        return PlainTextResponse(summary, media_type=CAPTURE_MEDIA_TYPE)
    except SyncRunError as exc:
        logger.exception("run-all sync failed")
        return _plain_error(str(exc))
    except Exception as exc:
        logger.exception("run-all sync unexpected error")
        return _plain_error(str(exc))


@app.get("/trello/review", response_class=PlainTextResponse)
async def trello_review(
    review_agent: TrelloReviewAgent = Depends(get_review_agent),
) -> PlainTextResponse:
    try:
        review = review_agent.review()
        save_trello_review(review)
        logger.info("trello review completed: %s", review.review_id)
        return PlainTextResponse(review.summary_text, media_type=CAPTURE_MEDIA_TYPE)
    except TrelloReviewError as exc:
        logger.exception("trello review failed")
        return _plain_error(str(exc))
    except Exception as exc:
        logger.exception("trello review unexpected error")
        return _plain_error(str(exc))


@app.post("/trello/apply-safe", response_class=PlainTextResponse)
async def trello_apply_safe(request: Request) -> PlainTextResponse:
    review_id: str | None = None
    try:
        raw_body = await request.body()
        if raw_body.strip():
            payload = json.loads(raw_body)
            review_id = ApplySafeRequest.model_validate(payload).review_id
    except (json.JSONDecodeError, ValidationError):
        return _plain_error("Invalid request body")

    review = get_trello_review(review_id) if review_id else get_latest_trello_review()
    if review is None:
        return _plain_error("No review found. Run GET /trello/review first.")

    try:
        result = apply_safe_actions(review)
        logger.info(
            "trello apply-safe review=%s applied=%s errors=%s",
            review.review_id,
            len(result.applied),
            len(result.errors),
        )
        return PlainTextResponse(result.to_plain_text(), media_type=CAPTURE_MEDIA_TYPE)
    except TrelloApplyError as exc:
        logger.exception("trello apply-safe failed")
        return _plain_error(str(exc))
    except Exception as exc:
        logger.exception("trello apply-safe unexpected error")
        return _plain_error(str(exc))


@app.get("/briefing/today", response_class=PlainTextResponse)
async def briefing_today(
    briefing: DailyBriefingService = Depends(get_briefing_service),
) -> PlainTextResponse:
    try:
        text = briefing.today()
        logger.info("daily briefing generated (%s chars)", len(text))
        return PlainTextResponse(text, media_type=CAPTURE_MEDIA_TYPE)
    except Exception as exc:
        logger.exception("daily briefing unexpected error")
        return _plain_error(str(exc))


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
