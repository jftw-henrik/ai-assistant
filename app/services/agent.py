import json
import logging
from datetime import date

from groq import APIError as GroqAPIError
from groq import Groq

from app.config import Settings
from app.integrations.trello import is_trello_available
from app.tools.registry import execute_tool, get_tools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Henrik Assistant, a personal productivity agent.

Today's date: {today}
Trello available: {trello_available}

Call one or more tools based on the user's message.

Date/time rule (highest priority):
If the input has a specific date, deadline, ddl, time, appointment, meeting, interview, delivery date, or due date:
1. Always call create_calendar_event with title and ISO 8601 start datetime.
2. If Trello is available, also call create_trello_card with the same title, notes, and due_date/date.

No-date rule:
If the input is a task, idea, or project without a specific date/time:
- If Trello is available → call create_trello_card only (main task store).
- If Trello is not available → call create_todo (legacy Google Tasks fallback).

Keyword hints:
- "todo", "to do", "task", "remember to", "remind me to" → task (Trello card, or legacy create_todo)
- "idea", "app idea", "project idea" → idea (Trello card)
- "project" without a date → project (Trello card)

Legacy:
- create_todo is legacy Google Tasks. Do not use it when Trello is available.
- Only use create_todo if Trello is not available, or the user explicitly asks for Google Tasks.

Examples:
- "Interview Friday at 14 with NZM" → create_calendar_event + create_trello_card (if available)
- "to do build a finance app" → create_trello_card (title: "Build a finance app")
- "idea build a finance app" → create_trello_card (title: "Build a finance app")
- "remember to call electrician" → create_trello_card (or create_todo if no Trello)

Extract clear titles. Strip leading keywords like "todo", "to do", "idea", "remember to".
Resolve relative dates using today's date as reference.
Use ISO 8601 datetimes for calendar events and ISO 8601 dates/datetimes for due dates."""


class AgentError(Exception):
    """Raised when the agent cannot complete a request."""


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self._client = Groq(api_key=settings.groq_api_key)
        self._model = settings.groq_model
        self._tools = get_tools()

    def run(self, text: str) -> list[str]:
        prompt = SYSTEM_PROMPT.format(
            today=date.today().isoformat(),
            trello_available="yes" if is_trello_available() else "no",
        )
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                temperature=0.1,
                tools=[tool.to_definition() for tool in self._tools],
                tool_choice="required",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text.strip()},
                ],
            )
        except GroqAPIError as exc:
            logger.exception("Groq API request failed")
            raise AgentError("Agent service unavailable") from exc

        message = completion.choices[0].message
        if not message.tool_calls:
            raise AgentError("Agent did not select a tool")

        executed_tools: list[str] = []
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            logger.info("agent chosen tool: %s", name)
            try:
                arguments = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as exc:
                logger.error("Invalid tool arguments: %s", tool_call.function.arguments)
                raise AgentError("Invalid tool arguments from agent") from exc

            try:
                execute_tool(name, arguments)
            except KeyError as exc:
                raise AgentError(str(exc)) from exc
            except RuntimeError as exc:
                logger.exception("Tool %s failed", name)
                raise AgentError(str(exc)) from exc
            except TypeError as exc:
                logger.error("Tool %s failed with arguments %s", name, arguments)
                raise AgentError(f"Tool {name} received invalid arguments") from exc

            executed_tools.append(name)

        logger.info("agent executed tools: %s", executed_tools)
        return executed_tools
