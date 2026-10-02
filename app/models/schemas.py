"""Strict Pydantic schemas for mock video editor tools and guided error handling."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# -----------------------------------------------------------------------------
# Common Enums & Types
# -----------------------------------------------------------------------------

class MaskShapeEnum(StrEnum):
    SILHOUETTE = "silhouette"
    CIRCLE = "circle"
    ROUNDED_RECT = "rounded_rect"
    ELLIPSE = "ellipse"
    BEZIER = "bezier"


class PiPPositionPresetEnum(StrEnum):
    TOP_RIGHT = "top-right"
    TOP_LEFT = "top-left"
    BOTTOM_RIGHT = "bottom-right"
    BOTTOM_LEFT = "bottom-left"
    CENTER = "center"
    CUSTOM = "custom"


class RenderFormatEnum(StrEnum):
    MP4 = "mp4"
    MOV = "mov"
    PRORES = "prores"
    WEBM = "webm"


# -----------------------------------------------------------------------------
# Guided Error Handling Schema
# -----------------------------------------------------------------------------

class ToolErrorResponse(BaseModel):
    """Structured error contract returned on tool exceptions to guide LLM recovery."""
    model_config = ConfigDict(extra="forbid")

    is_error: bool = Field(default=True, description="Always True when an error occurs.")
    error_code: str = Field(..., description="Machine-readable error identifier (e.g. TRACK_NOT_FOUND).")
    message: str = Field(..., description="Human-readable explanation of the validation or runtime failure.")
    recovery_instructions: str = Field(..., description="Explicit step-by-step instructions for the LLM on which tool to call next to fix this error.")
    suggested_tool: str | None = Field(None, description="Name of the tool the LLM should invoke next.")
    suggested_arguments: dict[str, Any] | None = Field(None, description="Recommended arguments to resolve the error.")


# -----------------------------------------------------------------------------
# TimelineAgent Schemas
# -----------------------------------------------------------------------------

class ClipMetadata(BaseModel):
    clip_id: str = Field(..., description="Unique clip identifier.")
    name: str = Field(..., description="Media source file name.")
    start_frame: int = Field(..., description="Timeline in-point frame index.")
    end_frame: int = Field(..., description="Timeline out-point frame index.")
    start_timecode: str = Field(..., description="Timeline in-point as SMPTE timecode HH:MM:SS:FF.")
    end_timecode: str = Field(..., description="Timeline out-point as SMPTE timecode HH:MM:SS:FF.")
    duration_seconds: float = Field(..., description="Clip duration in seconds.")
    has_mask: bool = Field(default=False, description="Whether a rotoscope mask is attached.")
    has_tracking: bool = Field(default=False, description="Whether motion tracking keyframes are attached.")


class TrackMetadata(BaseModel):
    track_id: str = Field(..., description="Track identifier (e.g. V1, V2, V3).")
    track_index: int = Field(..., description="Track vertical layer index (higher numbers sit above lower numbers).")
    track_name: str = Field(..., description="Descriptive track label.")
    clip_count: int = Field(..., description="Number of clips on this track.")
    clips: list[ClipMetadata] = Field(default_factory=list, description="Clips residing on this track.")


class GetTimelineStateInput(BaseModel):
    """Input parameters for inspecting the current timeline state."""
    model_config = ConfigDict(extra="forbid")

    track_filter: list[str] | None = Field(
        None,
        description="Optional list of track IDs (e.g. ['V1', 'V2']) to filter by. Defaults to all tracks."
    )


class GetTimelineStateOutput(BaseModel):
    """Output summary of timeline tracks, clips, and playhead position."""
    playhead_timecode: str = Field(..., description="Current playhead timecode in HH:MM:SS:FF format.")
    playhead_frame: int = Field(..., description="Current playhead frame index.")
    fps: float = Field(..., description="Timeline playback frame rate (e.g. 24.0).")
    resolution: str = Field(..., description="Timeline display resolution (e.g. '1920x1080').")
    total_duration_seconds: float = Field(..., description="Total timeline duration in seconds.")
    tracks: list[TrackMetadata] = Field(..., description="List of all video tracks and their clips.")
    active_masks_count: int = Field(..., description="Total number of active rotoscope masks.")
    active_motion_tracks_count: int = Field(..., description="Total number of active motion tracking trajectories.")
    active_pip_composites_count: int = Field(..., description="Total number of Picture-in-Picture composites.")


class SplitClipInput(BaseModel):
    """Input parameters to split a clip on a timeline track at a given timecode."""
    model_config = ConfigDict(extra="forbid")

    track_id: str = Field(..., description="Track ID where the target clip resides (e.g. 'V1').")
    clip_id: str = Field(..., description="Unique ID of the clip to split.")
    timecode: str = Field(
        ...,
        description="Split cut point as SMPTE timecode 'HH:MM:SS:FF' or numeric seconds '15.5'."
    )


class SplitClipOutput(BaseModel):
    """Output returned upon successful clip split."""
    status: str = Field(default="success")
    track_id: str = Field(..., description="Track containing the split clips.")
    original_clip_id: str = Field(..., description="Original clip ID.")
    new_clip_id_a: str = Field(..., description="First segment clip ID (left of cut).")
    new_clip_id_b: str = Field(..., description="Second segment clip ID (right of cut).")
    split_frame: int = Field(..., description="Frame index where the razor cut was made.")
    split_timecode: str = Field(..., description="Timecode where the cut was made.")
    clip_a_duration_seconds: float = Field(..., description="Duration of the first segment.")
    clip_b_duration_seconds: float = Field(..., description="Duration of the second segment.")


class UndoTimelineActionInput(BaseModel):
    """Input for undoing the previous timeline action."""
    model_config = ConfigDict(extra="forbid")


class UndoTimelineActionOutput(BaseModel):
    """Output returned when a previous action is restored from the undo stack."""
    status: str = Field(..., description="'success' or 'no_op'.")
    message: str = Field(..., description="Summary of the restored timeline state.")
    remaining_undo_steps: int = Field(default=0, description="Number of remaining undo snapshots.")
    track_count: int = Field(default=0, description="Active track count after restoration.")


# -----------------------------------------------------------------------------
# MaskAndTrackAgent Schemas
# -----------------------------------------------------------------------------

class TrackMotionInput(BaseModel):
    """Input parameters for calculating 2D motion tracking keyframes."""
    model_config = ConfigDict(extra="forbid")

    track_id: str = Field(..., description="Track ID containing the character/object footage (e.g. 'V1').")
    clip_id: str = Field(..., description="Clip ID to track.")
    target_label: str = Field(..., description="Semantic label for what to track (e.g. 'skater_face', 'runner').")
    start_timecode: str = Field(..., description="Tracking start in-point timecode ('HH:MM:SS:FF').")
    end_timecode: str = Field(..., description="Tracking end out-point timecode ('HH:MM:SS:FF').")
    sample_interval_frames: int = Field(
        default=1,
        ge=1,
        le=30,
        description="Keyframe sampling step (1 = every frame, 2 = every 2nd frame)."
    )


class TrackMotionOutput(BaseModel):
    """Output returned upon motion keyframe calculation."""
    status: str = Field(default="success")
    tracking_id: str = Field(..., description="Generated motion tracking identifier.")
    target_label: str = Field(..., description="Target object label.")
    clip_id: str = Field(..., description="Tracked clip ID.")
    frame_count: int = Field(..., description="Number of keyframes generated.")
    start_timecode: str = Field(..., description="Start timecode.")
    end_timecode: str = Field(..., description="End timecode.")
    keyframes_summary: str = Field(..., description="Compacted trajectory summary.")


class RotoscopeMaskInput(BaseModel):
    """Input parameters for generating a foreground rotoscope alpha matte."""
    model_config = ConfigDict(extra="forbid")

    track_id: str = Field(..., description="Track ID where the footage resides (e.g. 'V1').")
    clip_id: str = Field(..., description="Clip ID to isolate.")
    tracking_id: str | None = Field(None, description="Optional motion tracking ID to link mask position to.")
    mask_shape: MaskShapeEnum = Field(default=MaskShapeEnum.SILHOUETTE, description="Geometry shape of the mask.")
    feather_pixels: float = Field(default=2.0, ge=0.0, le=50.0, description="Soft edge feather radius in pixels.")
    invert: bool = Field(default=False, description="Whether to invert the mask (isolate background instead of foreground).")


class RotoscopeMaskOutput(BaseModel):
    """Output returned upon mask generation."""
    status: str = Field(default="success")
    mask_id: str = Field(..., description="Generated mask ID.")
    clip_id: str = Field(..., description="Clip ID the mask is attached to.")
    mask_shape: str = Field(..., description="Shape type.")
    feather_pixels: float = Field(..., description="Feather radius.")
    invert: bool = Field(..., description="Whether inverted.")
    tracking_linked: bool = Field(..., description="Whether connected to motion keyframes.")
    alpha_matte_type: str = Field(default="RGBA_ALPHAMATTE_8BIT")


# -----------------------------------------------------------------------------
# VFXCompositorAgent Schemas
# -----------------------------------------------------------------------------

class PinOverlayInput(BaseModel):
    """Input parameters for pinning an overlay asset to a motion tracking trajectory."""
    model_config = ConfigDict(extra="forbid")

    target_track_id: str = Field(..., description="Target track ID for the overlay (must be higher than base track, e.g. 'V2' or 'V3').")
    overlay_asset_id: str = Field(..., description="Asset identifier of the graphic/cutout to pin.")
    tracking_id: str = Field(..., description="Motion tracking ID containing the trajectory keyframes.")
    mask_id: str | None = Field(None, description="Optional rotoscope mask ID to apply to the overlay.")
    blend_mode: str = Field(default="normal", description="Compositing blend mode ('normal', 'multiply', 'screen', 'add').")
    opacity: float = Field(default=1.0, ge=0.0, le=1.0, description="Overlay layer opacity from 0.0 (transparent) to 1.0 (opaque).")


class PinOverlayOutput(BaseModel):
    """Output returned when overlay is pinned to trajectory."""
    status: str = Field(default="success")
    composite_clip_id: str = Field(..., description="Generated overlay clip ID.")
    target_track_id: str = Field(..., description="Track where overlay resides.")
    overlay_asset_id: str = Field(..., description="Asset ID.")
    tracking_id: str = Field(..., description="Attached motion tracking ID.")
    keyframes_attached: int = Field(..., description="Count of keyframes driving transform.")
    blend_mode: str = Field(..., description="Applied blend mode.")
    opacity: float = Field(..., description="Layer opacity.")


class MaskedPiPInput(BaseModel):
    """Input parameters for constructing a Picture-in-Picture composite."""
    model_config = ConfigDict(extra="forbid")

    base_track_id: str = Field(..., description="Lower track ID providing background footage (e.g. 'V1').")
    pip_track_id: str = Field(..., description="Upper track ID containing the PiP video window (e.g. 'V2' or 'V3').")
    pip_clip_id: str = Field(..., description="Clip ID on the upper track to scale into the PiP window.")
    position: PiPPositionPresetEnum = Field(default=PiPPositionPresetEnum.TOP_RIGHT, description="Position preset.")
    normalized_x: float = Field(default=0.75, ge=0.0, le=1.0, description="Normalized X center coordinate (0.0=left, 1.0=right).")
    normalized_y: float = Field(default=0.75, ge=0.0, le=1.0, description="Normalized Y center coordinate (0.0=bottom, 1.0=top).")
    scale: float = Field(default=0.28, ge=0.05, le=1.0, description="Scale factor relative to full frame.")
    mask_shape: MaskShapeEnum = Field(default=MaskShapeEnum.ROUNDED_RECT, description="Mask shape for the PiP window frame.")
    border_width: int = Field(default=4, ge=0, le=20, description="Border frame width in pixels.")
    border_color: str = Field(default="#FFFFFF", description="Border HEX color code (e.g. '#FFFFFF').")


class MaskedPiPOutput(BaseModel):
    """Output returned when Picture-in-Picture composite is created."""
    status: str = Field(default="success")
    pip_id: str = Field(..., description="Unique PiP composite configuration ID.")
    base_track_id: str = Field(..., description="Background track.")
    pip_track_id: str = Field(..., description="PiP track.")
    pip_clip_id: str = Field(..., description="PiP clip.")
    position_preset: str = Field(..., description="Position preset used.")
    coordinates: dict[str, float] = Field(..., description="Final normalized transform coordinates.")
    mask_shape: str = Field(..., description="Mask geometry applied.")
    border: str = Field(..., description="Border configuration.")


class RenderExportInput(BaseModel):
    """Input parameters for rendering and exporting the final timeline."""
    model_config = ConfigDict(extra="forbid")

    output_format: RenderFormatEnum = Field(default=RenderFormatEnum.MP4, description="Target container format ('mp4', 'mov', 'webm').")
    resolution: str = Field(default="1920x1080", description="Export frame resolution ('1920x1080', '3840x2160', '1080x1920').")
    fps: float = Field(default=24.0, ge=1.0, le=120.0, description="Target render frame rate.")
    render_preset: str = Field(default="ProRes_422", description="Mastering quality preset ('ProRes_422', 'H264_High', 'YouTube_1080p').")


class RenderExportOutput(BaseModel):
    """Output returned when timeline export is completed."""
    status: str = Field(default="success")
    render_job_id: str = Field(..., description="Render execution ID.")
    export_path: str = Field(..., description="Storage URI of exported video file.")
    resolution: str = Field(..., description="Rendered resolution.")
    fps: float = Field(..., description="Rendered fps.")
    format: str = Field(..., description="File container format.")
    preset: str = Field(..., description="Quality preset.")
    tracks_rendered: int = Field(..., description="Total tracks composited.")
    total_clips: int = Field(..., description="Total clips rendered.")
    pip_composites_applied: int = Field(..., description="PiP composites composited.")
    masks_applied: int = Field(..., description="Alpha masks rendered.")
    simulated_render_time_seconds: float = Field(..., description="Time taken to render in seconds.")
