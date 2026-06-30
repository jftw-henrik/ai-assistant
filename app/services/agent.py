import json
import logging
from datetime import date

from groq import APIError as GroqAPIError
from groq import Groq

from app.config import Settings
from app.integrations.trello import is_trello_available
from app.models.capture_result import CaptureBatchResult, CaptureItemResult
from app.services.input_splitter import split_capture_input
from app.services.trello_capture import TrelloCaptureError, route_capture
from app.tools.registry import execute_tool, get_tools

logger = logging.getLogger(__name__)

LEGACY_PROMPT = """You are Henrik Assistant, a personal productivity agent.

Today's date: {today}
Trello available: no

Call one tool based on the user's message.

If the input has a date/time/deadline → create_calendar_event.
Otherwise → create_todo for tasks/ideas/projects.

Extract clear titles. Resolve relative dates using today's date as reference.
Use ISO 8601 datetimes for calendar events and ISO 8601 dates for due dates."""


class AgentError(Exception):
    """Raised when the agent cannot complete a request."""


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = Groq(api_key=settings.groq_api_key)
        self._model = settings.groq_model
        self._tools = get_tools()

    def run(self, text: str) -> CaptureBatchResult:
        if is_trello_available():
            try:
                return route_capture(self._settings, text)
            except TrelloCaptureError as exc:
                raise AgentError(str(exc)) from exc

        return self._run_legacy_batch(text)

    def _run_legacy_batch(self, text: str) -> CaptureBatchResult:
        items = split_capture_input(text)
        results: list[CaptureItemResult] = []
        for item_text in items:
            actions = self._run_legacy_tools(item_text)
            results.append(
                CaptureItemResult(
                    text=item_text,
                    title=item_text,
                    list_name="Google Tasks",
                    actions=actions,
                )
            )
        return CaptureBatchResult(items=results)

    def _run_legacy_tools(self, text: str) -> list[str]:
        prompt = LEGACY_PROMPT.format(today=date.today().isoformat())
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
