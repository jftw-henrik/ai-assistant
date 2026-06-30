import json
import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from groq import APIError as GroqAPIError
from groq import Groq

from app.config import Settings, get_settings
from app.integrations.google_auth import GoogleAuthError
from app.integrations.google_calendar import (
    GoogleCalendarError,
    is_google_calendar_available,
    list_today_events,
)
from app.integrations.trello import TrelloError, fetch_board_snapshot, is_trello_available

logger = logging.getLogger(__name__)

BRIEFING_PROMPT = """You are a daily briefing assistant.

Write a concise, practical plain-text briefing for today using ONLY the provided data.
Do not invent tasks or events.

Use exactly these sections and headers:

Daily Briefing — {today}

📅 Today's Calendar
⚠️ Overdue Trello
📌 Due Today
⭐ Top 3 Recommended Tasks
🚧 Blocked / Stale
🗓 Suggested Plan for Today

Rules:
- Keep each section short with bullet points.
- Top 3 Recommended Tasks: pick the 3 most important actionable Trello cards for today.
- Blocked / Stale: only include cards that are clearly blocked or stale from the data; otherwise write "None obvious."
- Suggested Plan for Today: 3-5 short bullets weaving calendar and Trello priorities.
- If errors are listed, mention missing data briefly at the top.
- No markdown besides the section headers shown above.
"""


def _parse_card_due(due_value: str | None, timezone: str) -> date | None:
    if not due_value:
        return None
    parsed = datetime.fromisoformat(due_value.replace("Z", "+00:00"))
    return parsed.astimezone(ZoneInfo(timezone)).date()


def _classify_trello_cards(cards: list[dict[str, Any]], today: date, timezone: str) -> dict[str, Any]:
    overdue: list[dict[str, Any]] = []
    due_today: list[dict[str, Any]] = []
    no_due: list[dict[str, Any]] = []

    for card in cards:
        due = _parse_card_due(card.get("due"), timezone)
        entry = {
            "name": card.get("name"),
            "list_name": card.get("list_name"),
            "due": card.get("due"),
            "last_activity": card.get("last_activity"),
            "labels": card.get("labels", []),
        }
        if due is None:
            no_due.append(entry)
        elif due < today:
            overdue.append(entry)
        elif due == today:
            due_today.append(entry)

    return {
        "overdue": overdue,
        "due_today": due_today,
        "no_due_date": no_due,
        "open_cards": [
            {
                "name": card.get("name"),
                "list_name": card.get("list_name"),
                "due": card.get("due"),
                "last_activity": card.get("last_activity"),
                "labels": card.get("labels", []),
            }
            for card in cards
        ],
    }


def _collect_briefing_data() -> dict[str, Any]:
    settings = get_settings()
    timezone = settings.google_calendar_timezone
    today = datetime.now(ZoneInfo(timezone)).date()

    payload: dict[str, Any] = {
        "today": today.isoformat(),
        "timezone": timezone,
        "errors": [],
        "calendar_events": [],
        "trello": None,
    }

    if is_google_calendar_available():
        try:
            payload["calendar_events"] = list_today_events()
        except (GoogleCalendarError, GoogleAuthError) as exc:
            logger.exception("briefing calendar fetch failed")
            payload["errors"].append(f"Calendar: {exc}")
        except Exception as exc:
            logger.exception("briefing calendar unexpected failure")
            payload["errors"].append(f"Calendar: {exc}")
    else:
        payload["errors"].append("Calendar: not configured")

    if is_trello_available():
        try:
            snapshot = fetch_board_snapshot()
            payload["trello"] = _classify_trello_cards(snapshot.get("cards", []), today, timezone)
            payload["trello"]["lists"] = snapshot.get("lists", [])
        except TrelloError as exc:
            logger.exception("briefing trello fetch failed")
            payload["errors"].append(f"Trello: {exc}")
        except Exception as exc:
            logger.exception("briefing trello unexpected failure")
            payload["errors"].append(f"Trello: {exc}")
    else:
        payload["errors"].append("Trello: not configured")

    return payload


def _fallback_briefing(data: dict[str, Any]) -> str:
    lines = [f"Daily Briefing — {data['today']}", ""]
    if data["errors"]:
        lines.append("Note: " + "; ".join(data["errors"]))
        lines.append("")

    lines.append("📅 Today's Calendar")
    if data["calendar_events"]:
        for event in data["calendar_events"]:
            lines.append(f"  • {event['title']} ({event.get('start', '—')})")
    else:
        lines.append("  • None")

    trello = data.get("trello") or {}
    lines.extend(["", "⚠️ Overdue Trello"])
    for card in trello.get("overdue", [])[:10]:
        lines.append(f"  • {card['name']} ({card.get('list_name', '')})")
    if not trello.get("overdue"):
        lines.append("  • None")

    lines.extend(["", "📌 Due Today"])
    for card in trello.get("due_today", [])[:10]:
        lines.append(f"  • {card['name']} ({card.get('list_name', '')})")
    if not trello.get("due_today"):
        lines.append("  • None")

    lines.extend(
        [
            "",
            "⭐ Top 3 Recommended Tasks",
            "  • Review Trello board manually (briefing AI unavailable)",
            "",
            "🚧 Blocked / Stale",
            "  • None obvious.",
            "",
            "🗓 Suggested Plan for Today",
            "  • Start with calendar commitments.",
            "  • Clear overdue Trello cards.",
            "  • Finish due-today tasks.",
        ]
    )
    return "\n".join(lines)


class DailyBriefingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = Groq(api_key=self._settings.groq_api_key)
        self._model = self._settings.groq_model

    def today(self) -> str:
        data = _collect_briefing_data()
        prompt = BRIEFING_PROMPT.format(today=data["today"])
        user_content = json.dumps(data, ensure_ascii=True)

        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                temperature=0.3,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_content},
                ],
            )
        except GroqAPIError as exc:
            logger.exception("briefing Groq API request failed")
            return _fallback_briefing(data)

        content = completion.choices[0].message.content
        if not content:
            return _fallback_briefing(data)
        return content.strip()
