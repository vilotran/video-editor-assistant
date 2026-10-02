"""Unit tests for Pydantic input, output, and guided error schemas."""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    MaskedPiPInput,
    RenderExportInput,
    RenderFormatEnum,
    SplitClipInput,
    ToolErrorResponse,
)


def test_tool_error_response_schema():
    err = ToolErrorResponse(
        error_code="INVALID_TIMECODE",
        message="Timecode outside boundary",
        recovery_instructions="Call get_timeline_state() first",
        suggested_tool="get_timeline_state",
    )
    assert err.is_error is True
    assert err.error_code == "INVALID_TIMECODE"
    dump = err.model_dump()
    assert "recovery_instructions" in dump


def test_split_clip_input_validation():
    valid = SplitClipInput(track_id="V1", clip_id="clip_001", timecode="00:00:15:00")
    assert valid.track_id == "V1"

    # Extra forbidden parameters should raise validation error
    with pytest.raises(ValidationError):
        SplitClipInput(track_id="V1", clip_id="clip_001", timecode="00:00:15:00", extra_field=123)  # type: ignore


def test_pip_input_bounds():
    # Scale within bounds
    valid = MaskedPiPInput(
        base_track_id="V1",
        pip_track_id="V2",
        pip_clip_id="clip_002",
        scale=0.30,
        normalized_x=0.8,
        normalized_y=0.8,
    )
    assert valid.scale == 0.30

    # Scale out of bounds (< 0.05)
    with pytest.raises(ValidationError):
        MaskedPiPInput(
            base_track_id="V1",
            pip_track_id="V2",
            pip_clip_id="clip_002",
            scale=0.01,
        )


def test_render_export_enum_validation():
    valid = RenderExportInput(output_format=RenderFormatEnum.MP4, resolution="1920x1080")
    assert valid.output_format == RenderFormatEnum.MP4

    with pytest.raises(ValidationError):
        RenderExportInput(output_format="invalid_avi_format")  # type: ignore
