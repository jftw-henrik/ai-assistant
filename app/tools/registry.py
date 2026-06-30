from app.integrations.trello import is_trello_available
from app.tools.base import Tool
from app.tools.implementations import (
    CreateCalendarEventTool,
    CreateTodoTool,
    CreateTrelloCardTool,
)

_calendar_tool = CreateCalendarEventTool()
_todo_tool = CreateTodoTool()

_TOOLS: dict[str, Tool] = {
    _calendar_tool.name: _calendar_tool,
    _todo_tool.name: _todo_tool,
}

if is_trello_available():
    _trello_tool = CreateTrelloCardTool()
    _TOOLS[_trello_tool.name] = _trello_tool


def get_tools() -> list[Tool]:
    return list(_TOOLS.values())


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def execute_tool(name: str, arguments: dict) -> None:
    tool = get_tool(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    tool.execute(**arguments)
