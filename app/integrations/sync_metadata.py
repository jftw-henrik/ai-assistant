import re

GCAL_SOURCE_MARKER = "henrik-assistant:gcal:"


def gcal_source_marker(event_id: str) -> str:
    return f"{GCAL_SOURCE_MARKER}{event_id}"


def extract_gcal_event_id(description: str | None) -> str | None:
    if not description:
        return None
    match = re.search(rf"{re.escape(GCAL_SOURCE_MARKER)}([^\s\n]+)", description)
    return match.group(1) if match else None


def append_gcal_metadata(
    description: str | None,
    *,
    event_id: str,
    html_link: str | None = None,
) -> str:
    parts: list[str] = []
    if description and description.strip():
        parts.append(description.strip())
    parts.append(gcal_source_marker(event_id))
    parts.append("Source: google-calendar")
    if html_link:
        parts.append(f"Calendar: {html_link}")
    return "\n".join(parts)
