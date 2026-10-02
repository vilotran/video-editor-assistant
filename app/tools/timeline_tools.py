"""Timeline management tools for inspecting tracks, splitting clips, and undoing actions."""

from __future__ import annotations

from typing import Any

from app.engine.mock_engine import MockVideoEditorEngine
from app.models.schemas import (
    GetTimelineStateInput,
    GetTimelineStateOutput,
    SplitClipInput,
    SplitClipOutput,
    ToolErrorResponse,
    UndoTimelineActionOutput,
)
from app.observability.intent_outcome import IntentOutcomeAuditLogger
from app.observability.tracing import trace_span

# Singleton engine instance for mock timeline operations
default_engine = MockVideoEditorEngine()


def get_timeline_state(track_filter: list[str] | None = None) -> dict[str, Any]:
    """Inspects and returns the comprehensive current state of the mock NLE timeline.

    Use this tool to discover all available video tracks (V1, V2, V3, etc.), examine the
    clips positioned on each track, check their in/out frame boundaries and timecodes, read
    the active playhead position, and verify timeline resolution and frame rate.

    Args:
        track_filter: Optional list of track identifier strings (e.g. ['V1', 'V2'])
            to restrict the returned state. When omitted, all tracks are returned.

    Returns:
        A dictionary conforming to GetTimelineStateOutput detailing active tracks,
        clips, playhead position, and count of active masks, keyframe tracks, and PiP layouts.
        Returns a structured ToolErrorResponse if inspection fails.
    """
    with trace_span("tool.get_timeline_state", {"track_filter": str(track_filter)}):
        start_t = IntentOutcomeAuditLogger.log_intent(
            correlation_id="timeline_query",
            agent_name="TimelineAgent",
            tool_name="get_timeline_state",
            arguments={"track_filter": track_filter},
            intent_summary="Inspect timeline tracks, clips, and playhead position.",
        )
        try:
            validated_input = GetTimelineStateInput(track_filter=track_filter)
            state = default_engine.get_timeline_state(track_filter=validated_input.track_filter)
            output = GetTimelineStateOutput(**state).model_dump()
            IntentOutcomeAuditLogger.log_outcome(
                correlation_id="timeline_query",
                agent_name="TimelineAgent",
                tool_name="get_timeline_state",
                start_time=start_t,
                status="SUCCESS",
                result=output,
            )
            return output
        except Exception as exc:
            error_resp = ToolErrorResponse(
                error_code="TIMELINE_INSPECTION_FAILED",
                message=f"Failed to inspect timeline: {exc!s}",
                recovery_instructions="Call get_timeline_state without filters to inspect all existing tracks and reset query state.",
                suggested_tool="get_timeline_state",
                suggested_arguments={"track_filter": None},
            ).model_dump()
            IntentOutcomeAuditLogger.log_outcome(
                correlation_id="timeline_query",
                agent_name="TimelineAgent",
                tool_name="get_timeline_state",
                start_time=start_t,
                status="ERROR",
                result=error_resp,
                error=str(exc),
            )
            return error_resp


def split_clip_at_timecode(track_id: str, clip_id: str, timecode: str) -> dict[str, Any]:
    """Performs a razor split on a media clip residing on a video track at a specific timecode.

    Splits the target clip into two consecutive adjacent clips (Part A and Part B).
    The operation automatically saves an undo snapshot to permit rolling back.

    Args:
        track_id: Identifier of the track holding the target clip (e.g. 'V1', 'V2').
        clip_id: Unique clip identifier to be split (e.g. 'clip_base_001').
        timecode: Timecode cut point string in SMPTE 'HH:MM:SS:FF' format (e.g. '00:00:15:12')
            or numeric seconds (e.g. '15.5'). Must fall strictly within the clip duration.

    Returns:
        A dictionary conforming to SplitClipOutput confirming the razor cut, original
        and resulting clip IDs, split frame, and segment durations.
        If validation fails (invalid timecode or clip not found), returns a structured
        ToolErrorResponse with guided recovery instructions.
    """
    with trace_span("tool.split_clip_at_timecode", {"track_id": track_id, "clip_id": clip_id, "timecode": timecode}):
        start_t = IntentOutcomeAuditLogger.log_intent(
            correlation_id=f"split_{clip_id}",
            agent_name="TimelineAgent",
            tool_name="split_clip_at_timecode",
            arguments={"track_id": track_id, "clip_id": clip_id, "timecode": timecode},
            intent_summary=f"Split clip '{clip_id}' on track '{track_id}' at timecode '{timecode}'.",
        )
        try:
            validated_input = SplitClipInput(track_id=track_id, clip_id=clip_id, timecode=timecode)
            result = default_engine.split_clip_at_timecode(
                track_id=validated_input.track_id,
                clip_id=validated_input.clip_id,
                timecode=validated_input.timecode,
            )
            output = SplitClipOutput(**result).model_dump()
            IntentOutcomeAuditLogger.log_outcome(
                correlation_id=f"split_{clip_id}",
                agent_name="TimelineAgent",
                tool_name="split_clip_at_timecode",
                start_time=start_t,
                status="SUCCESS",
                result=output,
            )
            return output
        except KeyError as key_err:
            error_resp = ToolErrorResponse(
                error_code="CLIP_OR_TRACK_NOT_FOUND",
                message=str(key_err),
                recovery_instructions="Invoke get_timeline_state() to discover valid track IDs and active clip IDs before attempting a split.",
                suggested_tool="get_timeline_state",
                suggested_arguments={"track_filter": [track_id] if track_id else None},
            ).model_dump()
            IntentOutcomeAuditLogger.log_outcome(
                correlation_id=f"split_{clip_id}",
                agent_name="TimelineAgent",
                tool_name="split_clip_at_timecode",
                start_time=start_t,
                status="ERROR",
                result=error_resp,
                error=str(key_err),
            )
            return error_resp
        except ValueError as val_err:
            error_resp = ToolErrorResponse(
                error_code="INVALID_SPLIT_TIMECODE",
                message=str(val_err),
                recovery_instructions="Call get_timeline_state() to verify the clip start_timecode and end_timecode boundaries, then choose a timecode between them.",
                suggested_tool="get_timeline_state",
                suggested_arguments={"track_filter": [track_id]},
            ).model_dump()
            IntentOutcomeAuditLogger.log_outcome(
                correlation_id=f"split_{clip_id}",
                agent_name="TimelineAgent",
                tool_name="split_clip_at_timecode",
                start_time=start_t,
                status="ERROR",
                result=error_resp,
                error=str(val_err),
            )
            return error_resp
        except Exception as exc:
            error_resp = ToolErrorResponse(
                error_code="SPLIT_OPERATION_FAILED",
                message=f"Unexpected split failure: {exc!s}",
                recovery_instructions="Check timeline state and retry with valid SMPTE timecode.",
                suggested_tool="get_timeline_state",
                suggested_arguments=None,
            ).model_dump()
            return error_resp


def undo_last_timeline_action() -> dict[str, Any]:
    """Reverts the timeline state to the most recent pre-edit snapshot on the undo stack.

    Restores previous track configurations, clip positions, masks, motion tracking
    data, and Picture-in-Picture composites. Use this when a user requests to undo
    an edit or when an unintended cut occurred.

    Returns:
        A dictionary conforming to UndoTimelineActionOutput confirming the restoration,
        or reporting that the undo stack is empty.
    """
    with trace_span("tool.undo_last_timeline_action"):
        start_t = IntentOutcomeAuditLogger.log_intent(
            correlation_id="undo_action",
            agent_name="TimelineAgent",
            tool_name="undo_last_timeline_action",
            arguments={},
            intent_summary="Revert timeline to previous snapshot from undo stack.",
        )
        try:
            result = default_engine.undo_last_timeline_action()
            output = UndoTimelineActionOutput(**result).model_dump()
            IntentOutcomeAuditLogger.log_outcome(
                correlation_id="undo_action",
                agent_name="TimelineAgent",
                tool_name="undo_last_timeline_action",
                start_time=start_t,
                status="SUCCESS",
                result=output,
            )
            return output
        except Exception as exc:
            error_resp = ToolErrorResponse(
                error_code="UNDO_FAILED",
                message=f"Failed to restore undo snapshot: {exc!s}",
                recovery_instructions="Call get_timeline_state() to inspect the current state of the timeline.",
                suggested_tool="get_timeline_state",
                suggested_arguments=None,
            ).model_dump()
            return error_resp
