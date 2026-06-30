CONFIRMATIONS: dict[str, str] = {
    "create_calendar_event": "✅ Added to Google Calendar.",
    "create_trello_card": "✅ Added to Trello.",
    "update_trello_card": "✅ Updated Trello card.",
    "comment_trello_card": "✅ Comment added on Trello card.",
    "move_trello_done": "✅ Moved to Done on Trello.",
    "archive_trello_card": "✅ Archived Trello card.",
    "create_todo": "✅ Added to Google Tasks.",
    "save_idea": "💡 Saved as an idea.",
    "create_project": "📁 Saved as a project.",
}


def confirmation_for_tool(tool_name: str) -> str:
    return CONFIRMATIONS.get(tool_name, "✅ Done.")


def confirmation_for_tools(tool_names: list[str]) -> str:
    if not tool_names:
        return "✅ Done."

    unique = list(dict.fromkeys(tool_names))
    messages = [CONFIRMATIONS[name] for name in unique if name in CONFIRMATIONS]

    if "create_calendar_event" in unique and "create_trello_card" in unique:
        combined = "✅ Added to Google Calendar and Trello."
        rest = [m for m in messages if m not in {CONFIRMATIONS["create_calendar_event"], CONFIRMATIONS["create_trello_card"]}]
        if rest:
            return combined + " " + " ".join(rest)
        return combined

    if len(messages) == 1:
        return messages[0]
    if messages:
        return " ".join(messages)

    return "✅ Done."
