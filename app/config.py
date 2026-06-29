import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_DEFAULT_DB = Path("/tmp/henrik_assistant.db")


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    groq_model: str = "llama-3.3-70b-versatile"
    database_path: Path = _DEFAULT_DB
    google_client_id: str | None = None
    google_client_secret: str | None = None
    google_refresh_token: str | None = None
    google_client_secrets_file: Path | None = None
    google_calendar_id: str = "primary"
    google_calendar_timezone: str = "Europe/Stockholm"


@lru_cache
def get_settings() -> Settings:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is required")
    db_path = os.getenv("DATABASE_PATH")
    secrets_file = os.getenv("GOOGLE_CLIENT_SECRETS_FILE")
    return Settings(
        groq_api_key=api_key,
        groq_model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        database_path=Path(db_path) if db_path else _DEFAULT_DB,
        google_client_id=os.getenv("GOOGLE_CLIENT_ID"),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        google_refresh_token=os.getenv("GOOGLE_REFRESH_TOKEN"),
        google_client_secrets_file=Path(secrets_file) if secrets_file else None,
        google_calendar_id=os.getenv("GOOGLE_CALENDAR_ID", "primary"),
        google_calendar_timezone=os.getenv("GOOGLE_CALENDAR_TIMEZONE", "Europe/Stockholm"),
    )
