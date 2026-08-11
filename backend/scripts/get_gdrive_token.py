"""One-time script to get Google Drive OAuth2 refresh token.

Run this locally (not on server):
    python get_gdrive_token.py

It will open browser for Google login, then print the refresh token.
Set that token in your .env as GOOGLE_DRIVE_REFRESH_TOKEN.
"""
import sys

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    print("Install required package first:")
    print("  pip install google-auth-oauthlib")
    sys.exit(1)

SCOPES = ["https://www.googleapis.com/auth/drive"]

# Replace these with your OAuth2 client credentials
CLIENT_CONFIG = {
    "installed": {
        "client_id": "285659127128-fr3c3encv8lavurk1ul5idlj57ls5lvm.apps.googleusercontent.com",
        "client_secret": "GOCSPX-REPLACE_WITH_YOUR_FULL_SECRET_ENDING_50y2",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8080"],
    }
}


def main():
    print("=" * 60)
    print("  Google Drive OAuth2 — Get Refresh Token")
    print("=" * 60)
    print()

    if "YOUR_CLIENT_ID_HERE" in CLIENT_CONFIG["installed"]["client_id"]:
        print("ERROR: Edit this script first!")
        print("  Replace YOUR_CLIENT_ID_HERE and YOUR_CLIENT_SECRET_HERE")
        print("  with your OAuth2 credentials from Google Cloud Console.")
        print()
        print("  Get them at:")
        print("  https://console.cloud.google.com/apis/credentials")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
    credentials = flow.run_local_server(port=8080)

    print()
    print("=" * 60)
    print("  SUCCESS! Copy these to your backend .env:")
    print("=" * 60)
    print()
    print(f"GOOGLE_DRIVE_CLIENT_ID={CLIENT_CONFIG['installed']['client_id']}")
    print(f"GOOGLE_DRIVE_CLIENT_SECRET={CLIENT_CONFIG['installed']['client_secret']}")
    print(f"GOOGLE_DRIVE_REFRESH_TOKEN={credentials.refresh_token}")
    print()
    print("Done! You only need to run this once.")


if __name__ == "__main__":
    main()
