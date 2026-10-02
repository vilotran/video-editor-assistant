"""Unit tests for all 7 mock editing tools and guided error handling."""

from app.tools.mask_tools import (
    create_foreground_rotoscope_mask,
    track_character_motion_keyframes,
)
from app.tools.timeline_tools import (
    get_timeline_state,
    split_clip_at_timecode,
    undo_last_timeline_action,
)
from app.tools.vfx_tools import (
    create_masked_picture_in_picture,
    pin_character_overlay_to_track,
    render_mock_composite_export,
)


def test_get_timeline_state_tool():
    res = get_timeline_state()
    assert "tracks" in res
    assert "playhead_timecode" in res
    assert len(res["tracks"]) >= 3


def test_split_clip_guided_error_handling():
    # Non-existent clip triggers guided error recovery
    err = split_clip_at_timecode(track_id="V1", clip_id="clip_nonexistent", timecode="00:00:10:00")
    assert err.get("is_error") is True
    assert err.get("error_code") == "CLIP_OR_TRACK_NOT_FOUND"
    assert "recovery_instructions" in err
    assert err.get("suggested_tool") == "get_timeline_state"

    # Out of bounds timecode
    err2 = split_clip_at_timecode(track_id="V1", clip_id="clip_base_001", timecode="02:00:00:00")
    assert err2.get("is_error") is True
    assert err2.get("error_code") == "INVALID_SPLIT_TIMECODE"
    assert "recovery_instructions" in err2


def test_undo_timeline_action_tool():
    res = undo_last_timeline_action()
    assert "status" in res


def test_motion_tracking_guided_error():
    # Non-existent clip
    err = track_character_motion_keyframes(
        track_id="V99",
        clip_id="nonexistent",
        target_label="face",
        start_timecode="00:00:01:00",
        end_timecode="00:00:05:00",
    )
    assert err.get("is_error") is True
    assert "recovery_instructions" in err


def test_rotoscope_mask_tool():
    res = create_foreground_rotoscope_mask(
        track_id="V2",
        clip_id="clip_broll_001",
        mask_shape="rounded_rect",
        feather_pixels=2.0,
    )
    assert res.get("status") == "success"
    assert res.get("mask_id") is not None


def test_pin_overlay_guided_error():
    # Missing tracking_id
    err = pin_character_overlay_to_track(
        target_track_id="V3",
        overlay_asset_id="sunglasses.png",
        tracking_id="track_missing_id",
    )
    assert err.get("is_error") is True
    assert err.get("error_code") == "TRACKING_OR_TRACK_MISSING"
    assert err.get("suggested_tool") == "track_character_motion_keyframes"


def test_pip_composite_guided_error():
    # Invalid layer hierarchy (V2 over V2 or V1 over V2)
    err = create_masked_picture_in_picture(
        base_track_id="V2",
        pip_track_id="V1",
        pip_clip_id="clip_base_001",
    )
    assert err.get("is_error") is True
    assert err.get("error_code") == "INVALID_LAYER_HIERARCHY"
    assert "recovery_instructions" in err


def test_render_composite_export_tool():
    res = render_mock_composite_export(output_format="mp4", resolution="1920x1080")
    assert res.get("status") == "success"
    assert "export_path" in res
