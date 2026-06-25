"""ClipValidator — JSON structure and timestamp validation."""
import logging
from typing import Optional

from src.config import settings
from src.domain.entities import Clip
from src.domain.interfaces import IValidator

logger = logging.getLogger(__name__)

SUPPORTED_VERSIONS = ["1.0"]
REQUIRED_ROOT_FIELDS = ["version", "video_id", "language", "error", "clips"]
REQUIRED_CLIP_FIELDS = ["rank", "score", "start", "end", "hook", "reason", "subtitles"]
REQUIRED_WORD_FIELDS = ["word", "start", "end"]


class ClipValidator(IValidator):
    def validate_clip_result(
        self, data: dict, video_duration: float
    ) -> tuple[bool, list[str]]:
        """
        Validasi lengkap JSON output dari Gemini analysis.
        Returns: (is_valid, list_of_errors)
        """
        errors: list[str] = []

        # Cek version
        version = data.get("version")
        if version is None:
            errors.append("Field 'version' tidak ditemukan")
        elif version not in SUPPORTED_VERSIONS:
            errors.append(f"Versi '{version}' tidak didukung. Didukung: {SUPPORTED_VERSIONS}")

        # Cek required root fields
        for field in REQUIRED_ROOT_FIELDS:
            if field not in data:
                errors.append(f"Field root '{field}' tidak ditemukan")

        if errors:
            return False, errors

        # Cek clips array
        clips = data.get("clips")
        if not isinstance(clips, list):
            errors.append("Field 'clips' harus berupa array")
            return False, errors

        if len(clips) == 0:
            errors.append("Array 'clips' kosong — tidak ada clip yang ditemukan")
            return False, errors

        # Validasi per clip
        for i, clip in enumerate(clips):
            clip_prefix = f"clips[{i}]"

            # Cek required fields
            for field in REQUIRED_CLIP_FIELDS:
                if field not in clip:
                    errors.append(f"{clip_prefix}: field '{field}' tidak ditemukan")

            # Cek timestamp
            start = clip.get("start", 0)
            end = clip.get("end", 0)

            if start >= end:
                errors.append(
                    f"{clip_prefix}: start ({start}) >= end ({end})"
                )
            elif (end - start) < 1.0:
                errors.append(
                    f"{clip_prefix}: durasi terlalu pendek ({end - start:.1f}s, min 1.0s)"
                )

            if end > video_duration:
                errors.append(
                    f"{clip_prefix}: end ({end}) melebihi durasi video ({video_duration})"
                )

            # Validasi subtitles dan words
            subtitles = clip.get("subtitles", [])
            if isinstance(subtitles, list):
                for j, sub in enumerate(subtitles):
                    words = sub.get("words", [])
                    if isinstance(words, list):
                        for k, word in enumerate(words):
                            # Cek required word fields
                            for wf in REQUIRED_WORD_FIELDS:
                                if wf not in word:
                                    errors.append(
                                        f"{clip_prefix}.subtitles[{j}].words[{k}]: "
                                        f"field '{wf}' tidak ditemukan"
                                    )
                            # Normalize highlight
                            if "highlight" not in word:
                                word["highlight"] = False
                            else:
                                word["highlight"] = bool(word["highlight"])

        is_valid = len(errors) == 0
        return is_valid, errors

    def validate_clip_timestamps(
        self, clip: Clip, video_duration: float
    ) -> list[str]:
        """
        Validasi timestamp clip sebelum rendering/trimming.
        Returns: list error strings (kosong = valid)
        """
        errors: list[str] = []

        if clip.start < 0:
            errors.append(f"start negatif: {clip.start}")

        if clip.end <= clip.start:
            errors.append(f"end ({clip.end}) <= start ({clip.start})")

        if clip.end > video_duration:
            errors.append(
                f"end ({clip.end}) melebihi durasi video ({video_duration})"
            )

        duration = clip.end - clip.start
        if duration < settings.MIN_CLIP_DURATION:
            errors.append(
                f"durasi clip terlalu pendek: {duration:.1f}s (min {settings.MIN_CLIP_DURATION}s)"
            )

        return errors
