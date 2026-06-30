import json
import logging
import re
from datetime import date

from groq import APIError as GroqAPIError
from groq import Groq

from app.config import get_settings

logger = logging.getLogger(__name__)

SPLIT_PROMPT = """You split a voice/text capture message into separate actionable items.

Today's date: {today}

Each item should be one task, idea, deadline, meeting, or note that can be routed independently.
Preserve the original wording and language (Swedish/English) for each item.

Split on:
- commas
- "och" / "and" between distinct items
- semicolons
- distinct prefixes like "idé:" / "idea:"

Do NOT split:
- date/time phrases inside one item (e.g. "imorgon kl 10" stays with its task)
- a single coherent sentence with one action

Return ONLY valid JSON:
{{
  "items": ["item 1", "item 2"]
}}

If there is only one item, return a single-element array."""


class InputSplitError(Exception):
    """Raised when input splitting fails."""


def _looks_multi_item(text: str) -> bool:
    lower = text.lower()
    if "," in text or ";" in text:
        return True
    if re.search(r"\b(och|and)\b", lower):
        return True
    if len(re.findall(r"\b(idé|idea)\s*:", lower)) > 1:
        return True
    return False


def _split_with_groq(text: str) -> list[str]:
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key)

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SPLIT_PROMPT.format(today=date.today().isoformat())},
                {"role": "user", "content": json.dumps({"input": text}, ensure_ascii=True)},
            ],
        )
    except GroqAPIError as exc:
        logger.exception("Input split Groq API request failed")
        raise InputSplitError("Input split unavailable") from exc

    raw = completion.choices[0].message.content
    if not raw:
        raise InputSplitError("Empty input split response")

    try:
        data = json.loads(raw)
        items = [item.strip() for item in data.get("items", []) if str(item).strip()]
    except (json.JSONDecodeError, TypeError, AttributeError) as exc:
        logger.error("Invalid input split payload: %s", raw)
        raise InputSplitError("Invalid input split output") from exc

    if not items:
        raise InputSplitError("No items in split response")

    return items


def split_capture_input(text: str) -> list[str]:
    """Split multi-item capture text into separate routable items."""
    cleaned = text.strip()
    if not cleaned:
        return []

    if not _looks_multi_item(cleaned):
        logger.info("input split single item (heuristic)")
        return [cleaned]

    try:
        items = _split_with_groq(cleaned)
        if len(items) == 1:
            logger.info("input split single item (model)")
            return items
        logger.info("input split multi items count=%d items=%s", len(items), items)
        return items
    except InputSplitError as exc:
        logger.warning("input split fallback to single item: %s", exc)
        return [cleaned]
