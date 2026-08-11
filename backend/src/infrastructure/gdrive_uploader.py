"""Google Drive upload service.

Uses a service account to upload video files and make them publicly accessible.
All users share the same Drive storage (admin-managed service account).
"""
import logging
import os
from typing import Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from src.config import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


class GoogleDriveUploader:
    """Upload files to Google Drive via service account."""

    def __init__(self):
        self._service = None

    @property
    def is_configured(self) -> bool:
        """Check if Google Drive is configured."""
        return bool(
            settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE
            and os.path.exists(settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE)
        )

    def _get_service(self):
        """Lazy-init Drive API service."""
        if self._service is None:
            if not self.is_configured:
                raise RuntimeError("Google Drive service account not configured")
            credentials = service_account.Credentials.from_service_account_file(
                settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
            )
            self._service = build("drive", "v3", credentials=credentials)
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
        direct_link = f"https://drive.google.com/uc?export=download&id={file_id}"
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
            service.files().delete(fileId=file_id).execute()
            logger.info(f"Google Drive file deleted: {file_id}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete Drive file {file_id}: {e}")
            return False


# Singleton instance
gdrive_uploader = GoogleDriveUploader()
