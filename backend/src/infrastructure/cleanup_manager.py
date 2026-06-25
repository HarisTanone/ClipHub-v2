"""CleanupManager — handles temp file deletion in finally blocks."""
import logging
import os
import shutil
import fnmatch
from typing import List

from src.domain.entities import CleanupResult

logger = logging.getLogger(__name__)


class CleanupManager:
    """Handles temp file deletion in finally blocks.

    Preserves final outputs and removes temporary artifacts
    created during pipeline processing.
    """

    # Patterns for files that must NEVER be deleted
    PRESERVE_PATTERNS = [
        "*_final.mp4",
        "*_base.mp4",
        "*_raw.mp4",
        "*_metadata.json",
        "*_thumb.jpg",
        "original.mp4",
        "metadata.json",
    ]

    # Directories that must be preserved entirely
    PRESERVE_DIRS = ["raw", "thumbnail", "final"]

    # Patterns for temp files/dirs to delete
    TEMP_PATTERNS = [
        "temp_clip_*",  # temp clip directories
        "*_reframed.mp4",  # intermediate reframed clips
        "*_overlaid.mp4",  # intermediate overlaid clips
    ]

    TEMP_EXTENSIONS = [
        ".wav",  # extracted audio
    ]

    def cleanup_job_directory(self, job_dir: str) -> CleanupResult:
        """Delete temp files, preserve final outputs.

        Args:
            job_dir: Path to the job output directory.

        Returns:
            CleanupResult with counts of deleted and failed files.
        """
        files_deleted = 0
        files_failed = 0
        failed_paths: List[str] = []

        if not os.path.isdir(job_dir):
            logger.info("cleanup_skip", extra={"job_dir": job_dir, "reason": "directory not found"})
            return CleanupResult(files_deleted=0, files_failed=0, failed_paths=[])

        # Collect all items in the directory
        try:
            entries = os.listdir(job_dir)
        except OSError as e:
            logger.warning("cleanup_list_failed", extra={"job_dir": job_dir, "error": str(e)})
            return CleanupResult(files_deleted=0, files_failed=0, failed_paths=[])

        if not entries:
            logger.info("cleanup_empty", extra={"job_dir": job_dir, "reason": "no temp files found"})
            return CleanupResult(files_deleted=0, files_failed=0, failed_paths=[])

        for entry in entries:
            full_path = os.path.join(job_dir, entry)

            # Skip preserved files
            if self._should_preserve(entry):
                continue

            # Check if it's a temp item to delete
            if self._should_delete(entry):
                deleted, failed = self._delete_item(full_path)
                files_deleted += deleted
                files_failed += failed
                if failed > 0:
                    failed_paths.append(full_path)

        result = CleanupResult(
            files_deleted=files_deleted,
            files_failed=files_failed,
            failed_paths=failed_paths,
        )

        logger.info(
            "cleanup_complete",
            extra={
                "job_dir": job_dir,
                "files_deleted": result.files_deleted,
                "files_failed": result.files_failed,
            },
        )

        return result

    def _should_preserve(self, filename: str) -> bool:
        """Check if file matches any preserve pattern or is a preserved directory."""
        # Preserve directories entirely
        if filename in self.PRESERVE_DIRS:
            return True
        for pattern in self.PRESERVE_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                return True
        return False

    def _should_delete(self, filename: str) -> bool:
        """Check if file/dir matches temp patterns or extensions."""
        # Check directory patterns
        for pattern in self.TEMP_PATTERNS:
            if fnmatch.fnmatch(filename, pattern):
                return True

        # Check file extensions
        _, ext = os.path.splitext(filename)
        if ext.lower() in self.TEMP_EXTENSIONS:
            return True

        return False

    def _delete_item(self, path: str) -> tuple:
        """Delete a file or directory. Returns (deleted_count, failed_count)."""
        try:
            if os.path.isdir(path):
                # Count files in directory before deletion
                count = sum(len(files) for _, _, files in os.walk(path))
                shutil.rmtree(path)
                return (max(count, 1), 0)
            else:
                os.remove(path)
                return (1, 0)
        except OSError as e:
            logger.warning(
                "cleanup_delete_failed",
                extra={"path": path, "error": str(e)},
            )
            return (0, 1)
