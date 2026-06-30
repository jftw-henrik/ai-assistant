import json
import logging
import uuid
from datetime import date

from groq import APIError as GroqAPIError
from groq import Groq

from app.config import Settings, get_settings
from app.integrations.trello import TrelloError, fetch_board_snapshot, is_trello_available
from app.models.trello_review import BoardReviewResult, parse_review_payload

logger = logging.getLogger(__name__)

REVIEW_PROMPT = """You are a Trello board management analyst.

Today's date: {today}

Analyze the board snapshot and return ONLY valid JSON with this shape:
{{
  "findings": ["short issue or observation strings"],
  "safe_actions": [
    {{
      "type": "create_card|update_due_date|add_labels|create_calendar_event|update_calendar_event",
      "reason": "why",
      "card_id": "existing card id when relevant",
      "card_name": "card title for reference",
      "list_name": "target list for new cards",
      "title": "new card or event title",
      "notes": "optional card description",
      "due_date": "ISO 8601 due date",
      "labels": ["label names"],
      "date": "ISO 8601 calendar start datetime",
      "end_date": "optional ISO 8601 calendar end datetime",
      "event_id": "only for update_calendar_event when known"
    }}
  ],
  "advisory_only": [
    {{
      "type": "move_card|merge_cards|rename_card|archive_card|other",
      "card_id": "card id",
      "card_name": "card title",
      "suggested_list": "list name if relevant",
      "reason": "why this needs manual approval"
    }}
  ]
}}

Analyze for:
- urgency and importance
- stale items (no recent activity, old due dates, vague next steps)
- duplicates and near-duplicates
- unclear titles
- missing due dates on time-sensitive cards
- dependencies and blocked work
- tasks that are too broad and need supporting cards

Rules:
- Put only safe automations in safe_actions:
  - create_card for missing supporting cards
  - update_due_date when a due date should be added/fixed
  - add_labels for urgency/importance/type labels
  - create_calendar_event or update_calendar_event when a card has or needs a deadline/date
- Put list moves, archiving, renaming, deleting, and merges in advisory_only only.
- Suggest improved list placement only in advisory_only.
- Prefer concrete, minimal safe_actions.
- Use existing list names from the board.
- Use label names that fit the board; create simple clear label names when needed.
"""


class TrelloReviewError(Exception):
    """Raised when board review fails."""


def _format_review_text(
    review_id: str,
    findings: list[str],
    safe_actions: list,
    advisory_actions: list,
) -> str:
    lines = [
        "Trello Board Review",
        f"Review ID: {review_id}",
        "",
        "Findings:",
    ]
    if findings:
        lines.extend(f"  • {item}" for item in findings)
    else:
        lines.append("  • No major issues found.")

    lines.extend(["", f"Proposed safe changes ({len(safe_actions)}):"])
    if safe_actions:
        for index, action in enumerate(safe_actions, start=1):
            label = action.card_name or action.title or action.type
            lines.append(f"  {index}. [{action.type}] {label}")
            if action.reason:
                lines.append(f"     {action.reason}")
    else:
        lines.append("  • None")

    lines.extend(["", f"Manual approval needed ({len(advisory_actions)}):"])
    if advisory_actions:
        for index, item in enumerate(advisory_actions, start=1):
            label = item.card_name or item.type
            lines.append(f"  {index}. [{item.type}] {label}")
            if item.suggested_list:
                lines.append(f"     Move to: {item.suggested_list}")
            if item.reason:
                lines.append(f"     {item.reason}")
    else:
        lines.append("  • None")

    lines.extend(
        [
            "",
            "This review made no changes.",
            "Apply safe changes with POST /trello/apply-safe",
        ]
    )
    return "\n".join(lines)


class TrelloReviewAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = Groq(api_key=self._settings.groq_api_key)
        self._model = self._settings.groq_model

    def review(self) -> BoardReviewResult:
        if not is_trello_available():
            raise TrelloReviewError("Trello is not configured")

        try:
            snapshot = fetch_board_snapshot()
        except TrelloError as exc:
            raise TrelloReviewError(str(exc)) from exc

        prompt = REVIEW_PROMPT.format(today=date.today().isoformat())
        user_content = json.dumps(snapshot, ensure_ascii=True)

        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_content},
                ],
            )
        except GroqAPIError as exc:
            logger.exception("Trello review Groq API request failed")
            raise TrelloReviewError("Review service unavailable") from exc

        raw = completion.choices[0].message.content
        if not raw:
            raise TrelloReviewError("Empty review response")

        try:
            payload = json.loads(raw)
            findings, safe_actions, advisory_actions = parse_review_payload(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Invalid review payload: %s", raw)
            raise TrelloReviewError("Invalid review output") from exc

        review_id = str(uuid.uuid4())
        summary_text = _format_review_text(review_id, findings, safe_actions, advisory_actions)
        return BoardReviewResult(
            review_id=review_id,
            summary_text=summary_text,
            findings=findings,
            safe_actions=safe_actions,
            advisory_actions=advisory_actions,
        )
