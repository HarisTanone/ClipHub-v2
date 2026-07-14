import os
import sys

import pytest
from pydantic import ValidationError

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


def test_direct_edit_custom_hook_is_optional_and_normalized():
    assert UploadJobOptions(processing_mode="direct").custom_hook is None
    assert UploadJobOptions(processing_mode="direct", custom_hook="   ").custom_hook is None
    assert UploadJobOptions(
        processing_mode="direct",
        custom_hook="  Hook buatan user  ",
    ).custom_hook == "Hook buatan user"
    with pytest.raises(ValidationError):
        UploadJobOptions(processing_mode="direct", custom_hook="x" * 501)


if __name__ == "__main__":
    test_detection_is_portrait_only()
    test_upload_processing_modes_are_validated()
    test_direct_edit_custom_hook_is_optional_and_normalized()
    print("user requested option tests passed")
