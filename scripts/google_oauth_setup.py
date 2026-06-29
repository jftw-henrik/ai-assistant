#!/usr/bin/env python3
"""One-time OAuth2 setup to obtain GOOGLE_REFRESH_TOKEN."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

from app.integrations.google_auth import SCOPES

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env")


def _create_flow() -> InstalledAppFlow:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.\n"
            "Use a Desktop OAuth client from Google Cloud Console."
        )

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uris": ["http://localhost"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    return InstalledAppFlow.from_client_config(client_config, SCOPES)


def main() -> None:
    _load_env()

    flow = _create_flow()
    credentials = flow.run_local_server(
        port=0,
        open_browser=True,
        access_type="offline",
        prompt="consent",
    )

    if not credentials.refresh_token:
        raise SystemExit(
            "No refresh token received.\n"
            "Revoke this app's access at https://myaccount.google.com/permissions "
            "and run this script again."
        )

    print("\nAuthorization successful.\n")
    print("Add this to your .env file:\n")
    print(f"GOOGLE_REFRESH_TOKEN={credentials.refresh_token}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nAuthorization cancelled.")
