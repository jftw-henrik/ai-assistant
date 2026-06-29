CONFIRMATIONS: dict[str, str] = {
    "create_calendar_event": "✅ Added to Google Calendar.",
    "create_todo": "✅ Added to Google Tasks.",
    "save_idea": "💡 Saved as an idea.",
    "create_project": "📁 Saved as a project.",
}


def confirmation_for_tool(tool_name: str) -> str:
    try:
        return CONFIRMATIONS[tool_name]
    except KeyError:
        return "✅ Done."
