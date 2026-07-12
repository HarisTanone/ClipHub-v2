import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.infrastructure.aspect_ratio_router import AspectRatioRouter
from src.presentation.schemas.jobs import UploadJobOptions


def test_detection_is_portrait_only():
    router = AspectRatioRouter()
    assert router.route("9:16", True).autogrid_enabled is True
    assert router.route("16:9", True).autogrid_enabled is False
    assert router.route("1:1", True).autogrid_enabled is False


def test_upload_processing_modes_are_validated():
    assert UploadJobOptions(processing_mode="analyze").processing_mode == "analyze"
    assert UploadJobOptions(processing_mode="direct").processing_mode == "direct"


if __name__ == "__main__":
    test_detection_is_portrait_only()
    test_upload_processing_modes_are_validated()
    print("user requested option tests passed")