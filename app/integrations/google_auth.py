from functools import lru_cache

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build

from app.config import get_settings

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
TASKS_SCOPE = "https://www.googleapis.com/auth/tasks"

SCOPES = [CALENDAR_SCOPE, TASKS_SCOPE]


class GoogleAuthError(Exception):
    """Raised when Google OAuth credentials are missing or invalid."""


def _require_google_settings() -> None:
    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("GOOGLE_CLIENT_ID", settings.google_client_id),
            ("GOOGLE_CLIENT_SECRET", settings.google_client_secret),
            ("GOOGLE_REFRESH_TOKEN", settings.google_refresh_token),
        )
        if not value
    ]
    if missing:
        raise GoogleAuthError(f"Missing Google credentials: {', '.join(missing)}")


@lru_cache
def get_credentials() -> Credentials:
    _require_google_settings()
    settings = get_settings()
    return Credentials(
        token=None,
        refresh_token=settings.google_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )


def build_google_service(api_name: str, version: str) -> Resource:
    return build(
        api_name,
        version,
        credentials=get_credentials(),
        cache_discovery=False,
    )
