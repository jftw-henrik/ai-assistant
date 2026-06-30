import json
import logging
from datetime import date

from groq import APIError as GroqAPIError
from groq import Groq

from app.config import get_settings
from app.models.brain import BrainContext, BrainDecision

logger = logging.getLogger(__name__)

BRAIN_PROMPT = """You are Henrik's central Brain — a read-only analyst for voice/text capture.

Today's date: {today}

You receive user input plus context (Trello lists/cards, today's calendar, optional user profile).
You do NOT execute actions. Return a structured decision for downstream services.

Classify intent as one of:
- task: actionable work item
- idea: something to remember or explore later
- project: multi-step initiative or larger effort
- meeting: appointment, interview, call, or scheduled meeting
- deadline: date/time-bound item without a full meeting
- update: add info to an existing task/card
- complete: user marks work as done/finished
- note: general note without clear action

Choose area:
- work: client/professional work
- company: business/FIRMOR/admin entity tasks
- home: household
- personal: general personal life
- music: music production/client music work
- finance: money, invoices, accounting
- admin: paperwork, bureaucracy

Set urgency and importance (low | medium | high | critical) from language and deadlines.

Rules:
- Match existing Trello cards when the user clearly refers to the same task; set matched_card_id only when confident.
- confidence: 0.0–1.0 (use >=0.8 only when very sure about card match or intent).
- suggested_action=ask_clarification when intent or target is ambiguous.
- suggested_action=complete only when user clearly says done/klart/fixed/completed.
- suggested_action=archive only when user clearly wants archive/ta bort/rensa.
- has_deadline=true when a specific date/time/deadline is present or implied.
- deadline_datetime: ISO 8601 datetime when known, else null.
- target_systems: include trello for tasks/ideas/projects/updates/completions; calendar for meetings/deadlines with time; memory for notes/ideas without external action.
- title: short actionable title; summary: one sentence expansion.

Return ONLY valid JSON:
{{
  "intent": "task|idea|project|meeting|deadline|update|complete|note",
  "title": "string",
  "summary": "string",
  "project": "string or null",
  "area": "work|company|home|personal|music|finance|admin",
  "urgency": "low|medium|high|critical",
  "importance": "low|medium|high|critical",
  "has_deadline": false,
  "deadline_datetime": "ISO 8601 or null",
  "target_systems": ["trello", "calendar", "memory"],
  "suggested_action": "create|update|complete|archive|ask_clarification",
  "matched_card_id": "id or null",
  "confidence": 0.0,
  "reasoning": "short explanation"
}}"""


class BrainError(Exception):
    """Raised when Brain analysis fails."""


def _log_decision(text: str, decision: BrainDecision) -> None:
    logger.info(
        "brain decision intent=%s action=%s area=%s confidence=%.2f matched_card=%s targets=%s title=%r reasoning=%s",
        decision.intent,
        decision.suggested_action,
        decision.area,
        decision.confidence,
        decision.matched_card_id,
        decision.target_systems,
        decision.title,
        decision.reasoning,
    )
    logger.debug(
        "brain decision full text=%r payload=%s",
        text,
        decision.model_dump_json(),
    )


def analyze_input(text: str, context: BrainContext) -> BrainDecision:
    """Analyze user input and return a structured decision. Does not call Trello or Calendar."""
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    payload = {
        "input": text.strip(),
        "context": context.model_dump(mode="json"),
    }
    prompt = BRAIN_PROMPT.format(today=date.today().isoformat())

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
            ],
        )
    except GroqAPIError as exc:
        logger.exception("Brain Groq API request failed")
        raise BrainError("Brain analysis unavailable") from exc

    raw = completion.choices[0].message.content
    if not raw:
        raise BrainError("Empty Brain response")

    try:
        decision = BrainDecision.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Invalid Brain response payload: %s", raw)
        raise BrainError("Invalid Brain output") from exc

    _log_decision(text, decision)
    return decision
