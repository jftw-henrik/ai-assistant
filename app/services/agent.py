import json
import logging
from datetime import date

from groq import APIError as GroqAPIError
from groq import Groq

from app.config import Settings
from app.tools.registry import execute_tool, get_tools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Henrik Assistant, a personal productivity agent.

Today's date: {today}

Decide which tool to call based on the user's message. Always call exactly one tool.

Keyword rules (apply first):
- If the user says "todo", "to do", "task", "remember to", or "remind me to" → create_todo
- If the user says "idea", "app idea", or "project idea" → save_idea
- If unclear → create_todo

Examples:
- "to do build a finance app" → create_todo (title: "Build a finance app")
- "idea build a finance app" → save_idea (title: "Build a finance app")
- "remember to call electrician" → create_todo
- "Idea: Cubase MCP" → save_idea

Tool selection:
- create_calendar_event: meetings, appointments, interviews, events with a specific date and time
- create_todo: actionable tasks, reminders, things to remember or do (optionally with a due date)
- save_idea: ideas, brainstorms, concepts — not actionable tasks
- create_project: multi-step initiatives or named undertakings with broader scope than a single task

Extract clear titles from the input. Strip leading keywords like "todo", "to do", "idea", "remember to".
Resolve relative dates using today's date as reference.
Use ISO 8601 datetimes for calendar events and ISO 8601 dates for task due dates."""


class AgentError(Exception):
    """Raised when the agent cannot complete a request."""


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self._client = Groq(api_key=settings.groq_api_key)
        self._model = settings.groq_model
        self._tools = get_tools()

    def run(self, text: str) -> str:
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                temperature=0.1,
                tools=[tool.to_definition() for tool in self._tools],
                tool_choice="required",
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT.format(today=date.today().isoformat()),
                    },
                    {"role": "user", "content": text.strip()},
                ],
            )
        except GroqAPIError as exc:
            logger.exception("Groq API request failed")
            raise AgentError("Agent service unavailable") from exc

        message = completion.choices[0].message
        if not message.tool_calls:
            raise AgentError("Agent did not select a tool")

        tool_name = message.tool_calls[0].function.name
        logger.info("agent chosen tool: %s", tool_name)
        for tool_call in message.tool_calls:
            name = tool_call.function.name
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

        return tool_name
