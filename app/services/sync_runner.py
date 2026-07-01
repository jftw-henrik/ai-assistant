import logging

from app.config import Settings
from app.services.calendar_trello_sync import CalendarTrelloSyncError, sync_calendar_to_trello
from app.services.keep_trello_sync import KeepTrelloSyncError, sync_keep_to_trello

logger = logging.getLogger(__name__)


class SyncRunError(Exception):
    """Raised when all scheduled syncs fail."""


def run_all_syncs(settings: Settings) -> str:
    """Run all configured sync jobs and return a plain-text summary."""
    lines = ["Sync complete.", ""]
    successes = 0
    failures = 0

    try:
        calendar_result = sync_calendar_to_trello(settings)
        lines.append(f"Calendar → Trello: {calendar_result.to_plain_text()}")
        successes += 1
    except CalendarTrelloSyncError as exc:
        failures += 1
        lines.append(f"Calendar → Trello: ❌ {exc}")
        logger.exception("calendar-to-trello sync failed during run-all")
    except Exception as exc:
        failures += 1
        lines.append(f"Calendar → Trello: ❌ {exc}")
        logger.exception("calendar-to-trello sync unexpected error during run-all")

    try:
        keep_summary = sync_keep_to_trello(settings)
        lines.append(f"Keep → Trello: {keep_summary}")
        successes += 1
    except KeepTrelloSyncError as exc:
        failures += 1
        lines.append(f"Keep → Trello: ❌ {exc}")
        logger.exception("keep-to-trello sync failed during run-all")
    except Exception as exc:
        failures += 1
        lines.append(f"Keep → Trello: ❌ {exc}")
        logger.exception("keep-to-trello sync unexpected error during run-all")

    logger.info("run-all sync finished successes=%d failures=%d", successes, failures)

    if successes == 0 and failures > 0:
        raise SyncRunError("\n".join(lines))

    return "\n".join(lines)
