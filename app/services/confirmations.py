from app.models.capture_result import CaptureBatchResult, CaptureItemResult

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
        rest = [
            m
            for m in messages
            if m
            not in {
                CONFIRMATIONS["create_calendar_event"],
                CONFIRMATIONS["create_trello_card"],
            }
        ]
        if rest:
            return combined + " " + " ".join(rest)
        return combined

    if len(messages) == 1:
        return messages[0]
    if messages:
        return " ".join(messages)

    return "✅ Done."


def _format_item_destination(item: CaptureItemResult) -> str:
    destination = item.list_name or "To Do"
    if item.intent == "idea":
        destination = f"{destination}/Ideas"
    return destination


def _format_item_extras(item: CaptureItemResult) -> str:
    extras: list[str] = []
    if "create_calendar_event" in item.actions:
        extras.append("Calendar")
    if "update_trello_card" in item.actions:
        extras.append("Updated")
    if "move_trello_done" in item.actions:
        extras.append("Done")
    if "archive_trello_card" in item.actions:
        extras.append("Archived")
    if not extras:
        return ""
    return " + " + " + ".join(extras)


def format_capture_item_line(item: CaptureItemResult) -> str:
    return f"{_format_item_destination(item)} → {item.title}{_format_item_extras(item)}"


def confirmation_for_capture(batch: CaptureBatchResult) -> str:
    if len(batch.items) <= 1:
        return confirmation_for_tools(batch.all_actions)

    lines = [f"✅ Captured {len(batch.items)} items:"]
    for index, item in enumerate(batch.items, start=1):
        lines.append(f"{index}. {format_capture_item_line(item)}")
    return "\n".join(lines)
