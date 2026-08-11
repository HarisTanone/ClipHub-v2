"""One-time script to get Google Drive OAuth2 refresh token.

Run this locally (not on server):
    python get_gdrive_token.py

It will open browser for Google login, then print the refresh token.
Set that token in your .env as GOOGLE_DRIVE_REFRESH_TOKEN.
"""
import os
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Install required package first:")
    print("  pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/drive"]


def main():
    print("=" * 60)
    print("  Google Drive OAuth2 — Get Refresh Token")
    print("=" * 60)
    print()

    # Read from env or prompt
    client_id = os.environ.get("GOOGLE_DRIVE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET", "").strip()

    if not client_id:
        client_id = input("Enter Client ID: ").strip()
    if not client_secret:
        client_secret = input("Enter Client Secret: ").strip()

    if not client_id or not client_secret:
        print("ERROR: Client ID and Client Secret are required.")
        print("  Get them at: https://console.cloud.google.com/apis/credentials")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8080"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=8080)

    print()
    print("=" * 60)
    print("  SUCCESS! Copy these to your backend .env:")
    print("=" * 60)
    print()
    print(f"GOOGLE_DRIVE_CLIENT_ID={client_id}")
    print(f"GOOGLE_DRIVE_CLIENT_SECRET={client_secret}")
    print(f"GOOGLE_DRIVE_REFRESH_TOKEN={credentials.refresh_token}")
    print()
    print("Done! You only need to run this once.")


if __name__ == "__main__":
    main()
