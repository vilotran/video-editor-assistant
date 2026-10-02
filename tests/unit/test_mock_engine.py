"""Unit tests for MockVideoEditorEngine."""

import pytest

from app.engine.mock_engine import MockVideoEditorEngine


def test_initial_timeline_state():
    engine = MockVideoEditorEngine(fps=24.0)
    state = engine.get_timeline_state()
    assert state["fps"] == 24.0
    assert len(state["tracks"]) == 3
    track_ids = [t["track_id"] for t in state["tracks"]]
    assert "V1" in track_ids
    assert "V2" in track_ids
    assert "V3" in track_ids


def test_split_clip_and_undo():
    engine = MockVideoEditorEngine(fps=24.0)
    # Split clip_base_001 (duration 0..2400) at 00:00:10:00 (frame 240)
    res = engine.split_clip_at_timecode(track_id="V1", clip_id="clip_base_001", timecode="00:00:10:00")
    assert res["status"] == "success"
    assert res["split_frame"] == 240
    assert "clip_base_001" == res["new_clip_id_a"]
    assert res["new_clip_id_b"].startswith("clip_base_001_part2")

    # Verify track has 2 clips now
    state = engine.get_timeline_state(track_filter=["V1"])
    assert len(state["tracks"][0]["clips"]) == 2

    # Undo
    undo_res = engine.undo_last_timeline_action()
    assert undo_res["status"] == "success"
    state_after_undo = engine.get_timeline_state(track_filter=["V1"])
    assert len(state_after_undo["tracks"][0]["clips"]) == 1


def test_invalid_split_raises_error():
    engine = MockVideoEditorEngine(fps=24.0)
    # Timecode out of bounds (1000 seconds when clip is 100 seconds)
    with pytest.raises(ValueError):
        engine.split_clip_at_timecode("V1", "clip_base_001", "00:15:00:00")


def test_motion_tracking_keyframes():
    engine = MockVideoEditorEngine(fps=24.0)
    res = engine.track_character_motion_keyframes(
        track_id="V2",
        clip_id="clip_broll_001",
        target_label="actor_head",
        start_timecode="00:00:15:00",
        end_timecode="00:00:20:00",
    )
    assert res["status"] == "success"
    assert res["target_label"] == "actor_head"
    assert res["frame_count"] > 0
    tracking_id = res["tracking_id"]
    assert tracking_id in engine.motion_tracks


def test_rotoscope_mask_generation():
    engine = MockVideoEditorEngine(fps=24.0)
    res = engine.create_foreground_rotoscope_mask(
        track_id="V2",
        clip_id="clip_broll_001",
        mask_shape="silhouette",
        feather_pixels=3.0,
    )
    assert res["status"] == "success"
    mask_id = res["mask_id"]
    assert mask_id in engine.masks


def test_pin_character_overlay():
    engine = MockVideoEditorEngine(fps=24.0)
    track_res = engine.track_character_motion_keyframes(
        "V2", "clip_broll_001", "skater", "00:00:10:00", "00:00:20:00"
    )
    pin_res = engine.pin_character_overlay_to_track(
        target_track_id="V3",
        overlay_asset_id="helmet_cutout.png",
        tracking_id=track_res["tracking_id"],
    )
    assert pin_res["status"] == "success"
    assert pin_res["target_track_id"] == "V3"


def test_pip_layer_hierarchy_validation():
    engine = MockVideoEditorEngine(fps=24.0)
    # Attempting to put PiP on V1 over V2 (invalid hierarchy)
    with pytest.raises(ValueError):
        engine.create_masked_picture_in_picture(
            base_track_id="V2",
            pip_track_id="V1",
            pip_clip_id="clip_base_001",
        )

    # Valid hierarchy: PiP on V2 over V1
    pip_res = engine.create_masked_picture_in_picture(
        base_track_id="V1",
        pip_track_id="V2",
        pip_clip_id="clip_broll_001",
        position="top-right",
    )
    assert pip_res["status"] == "success"
    assert pip_res["pip_id"] in engine.pip_composites


def test_render_composite_export():
    engine = MockVideoEditorEngine(fps=24.0)
    res = engine.render_mock_composite_export(output_format="mp4", resolution="1920x1080")
    assert res["status"] == "success"
    assert res["format"] == "mp4"
    assert "mock://exports/final_cut_" in res["export_path"]
