CONFIRMATIONS: dict[str, str] = {
    "create_calendar_event": "✅ Added to Google Calendar.",
    "create_trello_card": "✅ Added to Trello.",
    "create_todo": "✅ Added to Google Tasks.",
    "save_idea": "💡 Saved as an idea.",
    "create_project": "📁 Saved as a project.",
}


def confirmation_for_tool(tool_name: str) -> str:
    return CONFIRMATIONS.get(tool_name, "✅ Done.")


def confirmation_for_tools(tool_names: list[str]) -> str:
    tools = set(tool_names)

    if "create_calendar_event" in tools and "create_trello_card" in tools:
        return "✅ Added to Google Calendar and Trello."

    if len(tool_names) == 1:
        return confirmation_for_tool(tool_names[0])

    messages = [CONFIRMATIONS[name] for name in tool_names if name in CONFIRMATIONS]
    if messages:
        return " ".join(messages)

    return "✅ Done."
