"""Automated Evaluation harness evaluating Video Editor Assistant against golden dataset."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import structlog

from app.engine.mock_engine import MockVideoEditorEngine
from app.guardrails.hitl import approval_gate
from app.tools.mask_tools import (
    create_foreground_rotoscope_mask,
    track_character_motion_keyframes,
)
from app.tools.timeline_tools import get_timeline_state, split_clip_at_timecode
from app.tools.vfx_tools import (
    create_masked_picture_in_picture,
    pin_character_overlay_to_track,
)

logger = structlog.get_logger("eval_runner")

DATASET_PATH = os.path.join(os.path.dirname(__file__), "datasets", "eval_dataset.jsonl")


def evaluate_scenario(scenario: dict[str, Any], engine: MockVideoEditorEngine) -> dict[str, Any]:
    """Executes and scores an individual evaluation scenario against the criteria."""
    s_id = scenario["id"]
    category = scenario["category"]
    passed = False
    details = {}

    if category == "timeline_cut":
        # 1. Inspect timeline state
        _ = get_timeline_state()
        # 2. Split clip at 00:00:15:00
        split_res = split_clip_at_timecode(track_id="V1", clip_id="clip_base_001", timecode="00:00:15:00")
        if split_res.get("status") == "success" and "new_clip_id_b" in split_res:
            passed = True
            details = {"split_frame": split_res["split_frame"], "clips_generated": 2}

    elif category == "motion_tracking":
        track_res = track_character_motion_keyframes(
            track_id="V2",
            clip_id="clip_broll_001",
            target_label="skater_face",
            start_timecode="00:00:10:00",
            end_timecode="00:00:20:00",
        )
        if track_res.get("status") == "success" and track_res.get("frame_count", 0) > 0:
            passed = True
            details = {"tracking_id": track_res["tracking_id"], "frames": track_res["frame_count"]}

    elif category == "rotoscope_mask":
        mask_res = create_foreground_rotoscope_mask(
            track_id="V2",
            clip_id="clip_broll_001",
            mask_shape="silhouette",
            feather_pixels=2.5,
        )
        if mask_res.get("status") == "success" and mask_res.get("mask_id"):
            passed = True
            details = {"mask_id": mask_res["mask_id"], "feather": mask_res["feather_pixels"]}

    elif category == "vfx_compositing":
        # Track first
        trk = track_character_motion_keyframes("V2", "clip_broll_001", "skater_face", "00:00:10:00", "00:00:20:00")
        pin_res = pin_character_overlay_to_track(
            target_track_id="V3",
            overlay_asset_id="animated_sunglasses.png",
            tracking_id=trk["tracking_id"],
        )
        if pin_res.get("status") == "success" and pin_res.get("composite_clip_id"):
            passed = True
            details = {"composite_clip_id": pin_res["composite_clip_id"], "track": pin_res["target_track_id"]}

    elif category == "picture_in_picture":
        pip_res = create_masked_picture_in_picture(
            base_track_id="V1",
            pip_track_id="V2",
            pip_clip_id="clip_broll_001",
            position="top-right",
            mask_shape="rounded_rect",
        )
        if pip_res.get("status") == "success" and pip_res.get("pip_id"):
            passed = True
            details = {"pip_id": pip_res["pip_id"], "position": pip_res["position_preset"]}

    elif category == "governance_hitl":
        # Check that approval gate halts unapproved render
        challenge = approval_gate.verify_or_challenge("render_mock_composite_export", {})
        if challenge and challenge.get("status") == "PENDING_HUMAN_APPROVAL":
            token = challenge["approval_token"]
            approval_gate.approve(token)
            # Re-verify passes after approval
            recheck = approval_gate.verify_or_challenge("render_mock_composite_export", {"approval_token": token})
            if recheck is None:
                passed = True
                details = {"hitl_challenged": True, "token_approved": True}

    elif category == "guided_error_recovery":
        err_res = split_clip_at_timecode(track_id="V99", clip_id="clip_nonexistent", timecode="invalid_timecode")
        if err_res.get("is_error") and "recovery_instructions" in err_res and err_res.get("suggested_tool") == "get_timeline_state":
            passed = True
            details = {"error_code": err_res["error_code"], "guided_recovery": True}

    return {
        "id": s_id,
        "category": category,
        "passed": passed,
        "details": details,
    }


def main() -> int:
    """Runs evaluation benchmark against all test scenarios in the golden dataset."""
    print("============================================================")
    print("  RUNNING AI VIDEO EDITOR ASSISTANT EVALUATION HARNESS")
    print("============================================================")

    if not os.path.exists(DATASET_PATH):
        print(f"Dataset path not found: {DATASET_PATH}")
        return 1

    scenarios = []
    with open(DATASET_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                scenarios.append(json.loads(line))

    engine = MockVideoEditorEngine()
    results = []
    passed_count = 0

    for sc in scenarios:
        res = evaluate_scenario(sc, engine)
        results.append(res)
        status_mark = "✓ PASS" if res["passed"] else "✗ FAIL"
        if res["passed"]:
            passed_count += 1
        print(f"[{status_mark}] {sc['id']:<32} ({sc['category']})")

    pass_rate = (passed_count / len(scenarios)) * 100.0
    print("------------------------------------------------------------")
    print(f"Total Scenarios: {len(scenarios)} | Passed: {passed_count} | Pass Rate: {pass_rate:.1f}%")
    print("============================================================")

    if pass_rate < 100.0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
