"""Google Drive upload service.

Supports two auth modes:
1. OAuth2 refresh token (Gmail personal) — preferred
2. Service account (Google Workspace with delegation)

All users share the same Drive storage (admin-managed credentials).
"""
import logging
import os
from typing import Optional

from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from src.config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive"]


class GoogleDriveUploader:
    """Upload files to Google Drive."""

    def __init__(self):
        self._service = None

    @property
    def is_configured(self) -> bool:
        """Check if Google Drive is configured (either OAuth2 or service account)."""
        has_oauth = bool(
            settings.GOOGLE_DRIVE_CLIENT_ID
            and settings.GOOGLE_DRIVE_CLIENT_SECRET
            and settings.GOOGLE_DRIVE_REFRESH_TOKEN
        )
        has_sa = bool(
            settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE
            and os.path.exists(settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE)
        )
        return has_oauth or has_sa

    def _get_service(self):
        """Lazy-init Drive API service."""
        if self._service is not None:
            return self._service

        if not self.is_configured:
            raise RuntimeError("Google Drive not configured")

        # Prefer OAuth2 refresh token (works with personal Gmail)
        if (settings.GOOGLE_DRIVE_CLIENT_ID
                and settings.GOOGLE_DRIVE_CLIENT_SECRET
                and settings.GOOGLE_DRIVE_REFRESH_TOKEN):
            credentials = Credentials(
                token=None,
                refresh_token=settings.GOOGLE_DRIVE_REFRESH_TOKEN,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=settings.GOOGLE_DRIVE_CLIENT_ID,
                client_secret=settings.GOOGLE_DRIVE_CLIENT_SECRET,
                scopes=SCOPES,
            )
            self._service = build("drive", "v3", credentials=credentials)
            logger.info("Google Drive: using OAuth2 refresh token")
            return self._service

        # Fallback: service account (Workspace with delegation)
        credentials = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        if settings.GOOGLE_DRIVE_DELEGATE_EMAIL:
            credentials = credentials.with_subject(settings.GOOGLE_DRIVE_DELEGATE_EMAIL)
        self._service = build("drive", "v3", credentials=credentials)
        logger.info("Google Drive: using service account")
        return self._service

    def upload_video(
        self,
        file_path: str,
        filename: Optional[str] = None,
        folder_id: Optional[str] = None,
    ) -> dict:
        """Upload a video file to Google Drive.

        Args:
            file_path: Local path to the video file
            filename: Name for the file in Drive (defaults to basename)
            folder_id: Drive folder ID (defaults to config GOOGLE_DRIVE_FOLDER_ID)

        Returns:
            dict with keys: file_id, web_view_link, direct_link
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Video file not found: {file_path}")

        service = self._get_service()
        target_folder = folder_id or settings.GOOGLE_DRIVE_FOLDER_ID
        file_name = filename or os.path.basename(file_path)

        # File metadata
        file_metadata = {"name": file_name}
        if target_folder:
            file_metadata["parents"] = [target_folder]

        # Detect mime type
        ext = os.path.splitext(file_path)[1].lower()
        mime_map = {
            ".mp4": "video/mp4",
            ".webm": "video/webm",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
        }
        mime_type = mime_map.get(ext, "video/mp4")

        # Upload
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,webViewLink",
            supportsAllDrives=True,
        ).execute()

        file_id = file.get("id")
        logger.info(f"Google Drive upload complete: {file_name} -> {file_id}")

        # Make publicly accessible (anyone with link can view)
        service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
            supportsAllDrives=True,
        ).execute()

        # Direct download link (usable by Repliz)
        # For publicly shared files, use this format which serves the file directly
        # without redirects or confirmation pages
        direct_link = f"https://drive.usercontent.google.com/download?id={file_id}&export=download"
        web_view_link = file.get("webViewLink", f"https://drive.google.com/file/d/{file_id}/view")

        logger.info(f"Google Drive file shared publicly: {direct_link}")

        return {
            "file_id": file_id,
            "web_view_link": web_view_link,
            "direct_link": direct_link,
        }

    def delete_file(self, file_id: str) -> bool:
        """Delete a file from Google Drive."""
        try:
            service = self._get_service()
            service.files().delete(fileId=file_id, supportsAllDrives=True).execute()
            logger.info(f"Google Drive file deleted: {file_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete Drive file {file_id}: {e}")
            return False


# Singleton instance
gdrive_uploader = GoogleDriveUploader()
