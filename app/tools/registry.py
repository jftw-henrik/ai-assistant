from app.tools.base import Tool
from app.tools.implementations import (
    CreateCalendarEventTool,
    CreateProjectTool,
    CreateTodoTool,
    SaveIdeaTool,
)

_TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        CreateCalendarEventTool(),
        CreateTodoTool(),
        SaveIdeaTool(),
        CreateProjectTool(),
    )
}


def get_tools() -> list[Tool]:
    return list(_TOOLS.values())


def get_tool(name: str) -> Tool | None:
    return _TOOLS.get(name)


def execute_tool(name: str, arguments: dict) -> None:
    tool = get_tool(name)
    if tool is None:
        raise KeyError(f"Unknown tool: {name}")
    tool.execute(**arguments)
