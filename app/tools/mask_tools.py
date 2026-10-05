"""Motion tracking and rotoscope masking tools."""

from __future__ import annotations

from typing import Any

from app.memory.compaction import HistoryCompactor
from app.models.schemas import (
    RotoscopeMaskInput,
    RotoscopeMaskOutput,
    ToolErrorResponse,
    TrackMotionInput,
    TrackMotionOutput,
)
from app.observability.intent_outcome import IntentOutcomeAuditLogger
from app.observability.tracing import trace_span
from app.tools.timeline_tools import default_engine


def track_character_motion_keyframes(
    track_id: str,
    clip_id: str,
    target_label: str,
    start_timecode: str,
    end_timecode: str,
    sample_interval_frames: int = 1,
) -> dict[str, Any]:
    """Generates 2D motion tracking keyframe vectors for a face or moving character in a clip.

    Analyzes character movement across the specified frame range and computes smooth
    frame-by-frame 2D transform keyframe vectors (frame, x, y, scale, rotation).
    The generated tracking_id can later be used to pin overlays or attach masks.

    Args:
        track_id: Identifier of the track holding the footage (e.g. 'V1').
        clip_id: Unique clip identifier containing the moving character (e.g. 'clip_broll_001').
        target_label: Semantic description of what is being tracked (e.g. 'skater_face', 'actor_head').
        start_timecode: Tracking in-point timecode in 'HH:MM:SS:FF' format (e.g. '00:00:10:00').
        end_timecode: Tracking out-point timecode in 'HH:MM:SS:FF' format (e.g. '00:00:20:00').
        sample_interval_frames: Keyframe step size (defaults to 1 for full continuous tracking).

    Returns:
        A dictionary conforming to TrackMotionOutput containing the generated tracking_id,
        keyframe count, and a compacted trajectory boundary summary.
        If validation fails, returns a structured ToolErrorResponse.
    """
    with trace_span("tool.track_character_motion_keyframes", {
        "track_id": track_id,
        "clip_id": clip_id,
        "target_label": target_label,
    }):
        start_t = IntentOutcomeAuditLogger.log_intent(
            correlation_id=f"track_{clip_id}",
            agent_name="MaskAndTrackAgent",
            tool_name="track_character_motion_keyframes",
            arguments={
                "track_id": track_id,
                "clip_id": clip_id,
                "target_label": target_label,
                "start_timecode": start_timecode,
                "end_timecode": end_timecode,
                "sample_interval_frames": sample_interval_frames,
            },
            intent_summary=f"Track motion of '{target_label}' on clip '{clip_id}' between {start_timecode} and {end_timecode}.",
        )
        try:
            validated = TrackMotionInput(
                track_id=track_id,
                clip_id=clip_id,
                target_label=target_label,
                start_timecode=start_timecode,
                end_timecode=end_timecode,
                sample_interval_frames=sample_interval_frames,
            )
            result = default_engine.track_character_motion_keyframes(
                track_id=validated.track_id,
                clip_id=validated.clip_id,
                target_label=validated.target_label,
                start_timecode=validated.start_timecode,
                end_timecode=validated.end_timecode,
                sample_interval_frames=validated.sample_interval_frames,
            )
            # Retrieve generated keyframes and compact them
            motion_track = default_engine.motion_tracks.get(result.get("tracking_id"))
            if motion_track and motion_track.keyframes:
                raw_keyframes = [
                    {"frame": k.frame, "x": k.x, "y": k.y, "scale": k.scale, "rotation": k.rotation}
                    for k in motion_track.keyframes
                ]
                compacted = HistoryCompactor.compact_keyframe_array(raw_keyframes)
                result["keyframes_summary"] = (
                    f"Compacted {compacted['frame_count']} keyframes ({compacted['frame_range']}): "
                    f"X: {compacted['x_bounds']}, Y: {compacted['y_bounds']}, Scale: {compacted['scale_bounds']}."
                )
            output = TrackMotionOutput(**result).model_dump()
            IntentOutcomeAuditLogger.log_outcome(
                correlation_id=f"track_{clip_id}",
                agent_name="MaskAndTrackAgent",
                tool_name="track_character_motion_keyframes",
                start_time=start_t,
                status="SUCCESS",
                result=output,
            )
            return output
        except KeyError as err:
            error_resp = ToolErrorResponse(
                error_code="CLIP_OR_TRACK_NOT_FOUND",
                message=str(err),
                recovery_instructions="Call get_timeline_state() to identify the valid track and clip IDs before tracking motion.",
                suggested_tool="get_timeline_state",
                suggested_arguments={"track_filter": [track_id] if track_id else None},
            ).model_dump()
            return error_resp
        except ValueError as val_err:
            error_resp = ToolErrorResponse(
                error_code="INVALID_TRACKING_TIMECODES",
                message=str(val_err),
                recovery_instructions="Ensure start_timecode is strictly earlier than end_timecode and within clip boundaries.",
                suggested_tool="get_timeline_state",
                suggested_arguments={"track_filter": [track_id]},
            ).model_dump()
            return error_resp
        except Exception as exc:
            error_resp = ToolErrorResponse(
                error_code="MOTION_TRACKING_FAILED",
                message=f"Motion tracking execution error: {exc!s}",
                recovery_instructions="Check input timecodes and retry with valid SMPTE format.",
                suggested_tool="get_timeline_state",
                suggested_arguments=None,
            ).model_dump()
            return error_resp


def create_foreground_rotoscope_mask(
    track_id: str,
    clip_id: str,
    tracking_id: str | None = None,
    mask_shape: str = "silhouette",
    feather_pixels: float = 2.0,
    invert: bool = False,
) -> dict[str, Any]:
    """Creates a rotoscope alpha matte mask isolating a moving character, face, or object.

    Generates a high-precision alpha matte channel on the target clip. The mask
    can optionally link to a motion tracking trajectory to dynamically follow movement.

    Args:
        track_id: Identifier of the track where the clip resides (e.g. 'V1' or 'V2').
        clip_id: Unique clip identifier to isolate (e.g. 'clip_broll_001').
        tracking_id: Optional motion tracking identifier generated by
            track_character_motion_keyframes to bind the mask coordinate origin to.
        mask_shape: Geometry of the mask ('silhouette', 'circle', 'rounded_rect', 'bezier').
        feather_pixels: Edge feathering radius in pixels for smooth alpha blending (0.0 to 50.0).
        invert: If True, inverts alpha matte to mask out the foreground subject.

    Returns:
        A dictionary conforming to RotoscopeMaskOutput detailing the created mask_id,
        applied geometry shape, feathering, and linkage status.
        If validation fails, returns a structured ToolErrorResponse.
    """
    with trace_span("tool.create_foreground_rotoscope_mask", {
        "track_id": track_id,
        "clip_id": clip_id,
        "mask_shape": mask_shape,
    }):
        start_t = IntentOutcomeAuditLogger.log_intent(
            correlation_id=f"mask_{clip_id}",
            agent_name="MaskAndTrackAgent",
            tool_name="create_foreground_rotoscope_mask",
            arguments={
                "track_id": track_id,
                "clip_id": clip_id,
                "tracking_id": tracking_id,
                "mask_shape": mask_shape,
                "feather_pixels": feather_pixels,
                "invert": invert,
            },
            intent_summary=f"Create rotoscope mask '{mask_shape}' on clip '{clip_id}'.",
        )
        try:
            validated = RotoscopeMaskInput(
                track_id=track_id,
                clip_id=clip_id,
                tracking_id=tracking_id,
                mask_shape=mask_shape,  # type: ignore
                feather_pixels=feather_pixels,
                invert=invert,
            )
            result = default_engine.create_foreground_rotoscope_mask(
                track_id=validated.track_id,
                clip_id=validated.clip_id,
                tracking_id=validated.tracking_id,
                mask_shape=validated.mask_shape.value,
                feather_pixels=validated.feather_pixels,
                invert=validated.invert,
            )
            output = RotoscopeMaskOutput(**result).model_dump()
            IntentOutcomeAuditLogger.log_outcome(
                correlation_id=f"mask_{clip_id}",
                agent_name="MaskAndTrackAgent",
                tool_name="create_foreground_rotoscope_mask",
                start_time=start_t,
                status="SUCCESS",
                result=output,
            )
            return output
        except KeyError as err:
            error_resp = ToolErrorResponse(
                error_code="TARGET_OR_TRACKING_NOT_FOUND",
                message=str(err),
                recovery_instructions="Verify the clip_id with get_timeline_state() or ensure track_character_motion_keyframes() was called before linking tracking_id.",
                suggested_tool="get_timeline_state",
                suggested_arguments={"track_filter": [track_id] if track_id else None},
            ).model_dump()
            return error_resp
        except Exception as exc:
            error_resp = ToolErrorResponse(
                error_code="ROTOSCOPE_MASK_FAILED",
                message=f"Failed to generate rotoscope mask: {exc!s}",
                recovery_instructions="Ensure mask_shape is one of ['silhouette', 'circle', 'rounded_rect', 'bezier'] and feather_pixels is <= 50.0.",
                suggested_tool="create_foreground_rotoscope_mask",
                suggested_arguments={"mask_shape": "silhouette", "feather_pixels": 2.0},
            ).model_dump()
            return error_resp
