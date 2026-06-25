"""CheckpointManager — atomic JSON checkpoint write/read for pipeline resume."""
import json
import logging
import os
import glob
import tempfile
from datetime import datetime, timezone
from typing import Optional, Any

from src.domain.entities import CheckpointData

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages pipeline checkpoints for resume-from-failure.
    
    Uses atomic write-to-temp-then-rename pattern to prevent corruption.
    """

    CHECKPOINT_DIR = "tmp/checkpoints"

    def __init__(self, base_dir: Optional[str] = None):
        self._base_dir = base_dir or os.path.join(os.getcwd(), self.CHECKPOINT_DIR)
        os.makedirs(self._base_dir, exist_ok=True)

    def save(self, job_id: str, step_number: int, step_name: str, output_data: Any) -> None:
        """Write checkpoint atomically (write-temp-rename pattern).
        
        Args:
            job_id: Unique job identifier.
            step_number: Pipeline step number (1-indexed).
            step_name: Human-readable step name.
            output_data: Serializable output from the step.
        """
        checkpoint = {
            "job_id": job_id,
            "step_number": step_number,
            "step_name": step_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "output_data": output_data,
        }

        filename = f"{job_id}_step{step_number}.json"
        target_path = os.path.join(self._base_dir, filename)

        # Atomic write: write to temp file, then rename
        fd, tmp_path = tempfile.mkstemp(dir=self._base_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(checkpoint, f, ensure_ascii=False, default=str)
            os.replace(tmp_path, target_path)
            logger.info("checkpoint_saved", extra={"job_id": job_id, "step": step_number, "step_name": step_name})
        except Exception as e:
            # Clean up temp file on failure
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            logger.error("checkpoint_save_failed", extra={"job_id": job_id, "step": step_number, "error": str(e)})
            raise

    def get_last_checkpoint(self, job_id: str) -> Optional[CheckpointData]:
        """Find highest completed step for job_id.
        
        Returns:
            CheckpointData for highest step, or None if no valid checkpoints exist.
        """
        pattern = os.path.join(self._base_dir, f"{job_id}_step*.json")
        files = glob.glob(pattern)

        if not files:
            return None

        best: Optional[CheckpointData] = None
        best_step = -1

        for filepath in files:
            data = self._load_checkpoint_file(filepath)
            if data and data.step_number > best_step:
                best = data
                best_step = data.step_number

        return best

    def cleanup(self, job_id: str) -> None:
        """Delete all checkpoints for completed job."""
        pattern = os.path.join(self._base_dir, f"{job_id}_step*.json")
        files = glob.glob(pattern)

        for filepath in files:
            try:
                os.unlink(filepath)
            except OSError as e:
                logger.warning("checkpoint_cleanup_failed", extra={"path": filepath, "error": str(e)})

        if files:
            logger.info("checkpoint_cleanup", extra={"job_id": job_id, "files_deleted": len(files)})

    def _load_checkpoint_file(self, filepath: str) -> Optional[CheckpointData]:
        """Load and validate a checkpoint file.
        
        Returns None and logs if file is invalid JSON or missing required fields.
        """
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("checkpoint_invalid", extra={"path": filepath, "error": str(e)})
            return None

        # Validate required fields
        required = ("job_id", "step_number", "step_name")
        for field in required:
            if field not in data:
                logger.warning("checkpoint_missing_field", extra={"path": filepath, "field": field})
                return None

        return CheckpointData(
            job_id=data["job_id"],
            step_number=data["step_number"],
            step_name=data["step_name"],
            timestamp=data.get("timestamp", ""),
            output_data=data.get("output_data"),
        )
