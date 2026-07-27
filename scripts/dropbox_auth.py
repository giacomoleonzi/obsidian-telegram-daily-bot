#!/usr/bin/env python3
"""One-time helper to obtain a Dropbox OAuth2 refresh token.

Run on any machine with Python and the dropbox package installed:
    pip install dropbox
    python scripts/dropbox_auth.py
"""

from __future__ import annotations

import os
import sys

try:
    import dropbox
except ImportError:
    print("Error: 'dropbox' package not installed. Run: pip install dropbox")
    sys.exit(1)


def main() -> None:
    app_key = os.getenv("DROPBOX_APP_KEY") or ""
    app_secret = os.getenv("DROPBOX_APP_SECRET") or ""

    if not app_key:
        app_key = input("Dropbox App Key: ").strip()
    if not app_secret:
        app_secret = input("Dropbox App Secret: ").strip()

    if not app_key or not app_secret:
        print("Error: App Key and App Secret are required.")
        sys.exit(1)

    auth_flow = dropbox.DropboxOAuth2FlowNoRedirect(
        consumer_key=app_key,
        consumer_secret=app_secret,
        token_access_type="offline",
    )

    authorize_url = auth_flow.start()
    print()
    print("1. Open this URL in any browser:")
    print(f"   {authorize_url}")
    print()
    print("2. Authorize the app and copy the code shown.")
    print()
    auth_code = input("3. Paste the authorization code here: ").strip()

    if not auth_code:
        print("Error: no authorization code provided.")
        sys.exit(1)

    try:
        result = auth_flow.finish(auth_code)
    except Exception as exc:
        print(f"Error exchanging code: {exc}")
        sys.exit(1)

    print()
    print(f"DROPBOX_REFRESH_TOKEN={result.refresh_token}")
    print()
    print("Add this to your config/.env file.")


if __name__ == "__main__":
    main()
