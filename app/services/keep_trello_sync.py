import logging

from app.config import Settings

logger = logging.getLogger(__name__)


class KeepTrelloSyncError(Exception):
    """Raised when Keep-to-Trello sync fails."""


def sync_keep_to_trello(settings: Settings) -> str:
    """Placeholder for future Google Keep → Trello sync."""
    _ = settings
    logger.info("keep-to-trello sync: placeholder, not implemented")
    return "Not implemented yet (skipped)."
