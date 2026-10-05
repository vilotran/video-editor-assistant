"""Thread-safe Mock Video Editor Engine simulating multi-track NLE timelines and compositing."""

from __future__ import annotations

import copy
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class KeyframeVector:
    """Represents a 2D spatial transform keyframe for motion tracking."""
    frame: int
    x: float
    y: float
    scale: float
    rotation: float


@dataclass
class MockClip:
    """Represents an audio/video media clip residing on a timeline track."""
    clip_id: str
    name: str
    start_frame: int
    end_frame: int
    source_duration_frames: int
    media_path: str = "mock://assets/footage.mp4"
    transform: dict[str, float] = field(default_factory=lambda: {"x": 0.5, "y": 0.5, "scale": 1.0, "rotation": 0.0})
    mask_id: str | None = None
    tracking_id: str | None = None


@dataclass
class MockTrack:
    """Represents a single video track band (e.g. V1, V2, V3)."""
    track_id: str
    track_index: int
    track_name: str
    clips: list[MockClip] = field(default_factory=list)
    is_muted: bool = False
    is_locked: bool = False


@dataclass
class MockRotoscopeMask:
    """Represents a foreground rotoscope alpha matte."""
    mask_id: str
    clip_id: str
    mask_shape: str
    feather_pixels: float
    invert: bool
    created_at_frame: int


@dataclass
class MockMotionTrack:
    """Represents computed motion tracking keyframe trajectory."""
    tracking_id: str
    clip_id: str
    target_label: str
    start_frame: int
    end_frame: int
    keyframes: list[KeyframeVector]


@dataclass
class MockPiPComposite:
    """Represents a Picture-in-Picture layout configuration."""
    pip_id: str
    base_track_id: str
    pip_track_id: str
    pip_clip_id: str
    position: str
    normalized_x: float
    normalized_y: float
    scale: float
    mask_shape: str
    border_width: int
    border_color: str


class MockVideoEditorEngine:
    """In-memory, thread-safe mock video editing & compositing engine."""

    def __init__(self, fps: float = 24.0, width: int = 1920, height: int = 1080) -> None:
        self._lock = threading.RLock()
        self.fps = fps
        self.width = width
        self.height = height
        self.playhead_frame: int = 0
        self.tracks: dict[str, MockTrack] = {}
        self.masks: dict[str, MockRotoscopeMask] = {}
        self.motion_tracks: dict[str, MockMotionTrack] = {}
        self.pip_composites: dict[str, MockPiPComposite] = {}
        self.undo_stack: list[dict[str, Any]] = []
        self._initialize_default_timeline()

    def _initialize_default_timeline(self) -> None:
        """Initializes default video tracks (V1, V2, V3) and baseline footage."""
        with self._lock:
            # Track V1: Primary baseline footage (Background)
            track_v1 = MockTrack(track_id="V1", track_index=1, track_name="Main Video")
            track_v1.clips.append(
                MockClip(
                    clip_id="clip_base_001",
                    name="main_interview_cam_a.mp4",
                    start_frame=0,
                    end_frame=2400,  # 100 seconds at 24 fps
                    source_duration_frames=2400,
                )
            )

            # Track V2: Overlay / B-roll track
            track_v2 = MockTrack(track_id="V2", track_index=2, track_name="Overlay Video")
            track_v2.clips.append(
                MockClip(
                    clip_id="clip_broll_001",
                    name="skater_action_cam_b.mp4",
                    start_frame=240,
                    end_frame=1200,
                    source_duration_frames=1200,
                )
            )

            # Track V3: Graphics / PIP track
            track_v3 = MockTrack(track_id="V3", track_index=3, track_name="Graphics & PIP")

            self.tracks = {"V1": track_v1, "V2": track_v2, "V3": track_v3}
            self.playhead_frame = 240  # 10.0 seconds default

    def _save_snapshot(self) -> None:
        """Pushes current timeline state onto the undo stack."""
        state_copy = {
            "playhead_frame": self.playhead_frame,
            "tracks": copy.deepcopy(self.tracks),
            "masks": copy.deepcopy(self.masks),
            "motion_tracks": copy.deepcopy(self.motion_tracks),
            "pip_composites": copy.deepcopy(self.pip_composites),
        }
        self.undo_stack.append(state_copy)
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

        try:
            from app.memory.async_memory import dispatch_async_memory_consolidation

            dispatch_async_memory_consolidation(
                session_id="default_session",
                timeline_state=self.get_timeline_state(),
                turn_index=len(self.undo_stack),
            )
        except Exception:
            pass

    def timecode_to_frame(self, timecode: str) -> int:
        """Converts HH:MM:SS:FF or SS string to timeline integer frame number."""
        parts = timecode.strip().split(":")
        if len(parts) == 4:
            hours, minutes, seconds, frames = map(int, parts)
            total_seconds = hours * 3600 + minutes * 60 + seconds
            return int(total_seconds * self.fps + frames)
        elif len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            return int((hours * 3600 + minutes * 60 + seconds) * self.fps)
        elif len(parts) == 1:
            try:
                seconds_val = float(parts[0])
                return int(seconds_val * self.fps)
            except ValueError:
                pass
        raise ValueError(f"Invalid timecode format: '{timecode}'. Expected 'HH:MM:SS:FF' or numeric seconds.")

    def frame_to_timecode(self, frame: int) -> str:
        """Converts timeline integer frame number into standard SMPTE 'HH:MM:SS:FF' string."""
        total_seconds = int(frame / self.fps)
        rem_frames = int(frame % self.fps)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{rem_frames:02d}"

    def get_timeline_state(self, track_filter: list[str] | None = None) -> dict[str, Any]:
        """Returns the full state of active tracks, clips, and playhead."""
        with self._lock:
            tracks_info = []
            max_frame = 0
            for t_id, track in sorted(self.tracks.items(), key=lambda x: x[1].track_index):
                if track_filter and t_id not in track_filter:
                    continue
                clips_info = []
                for clip in track.clips:
                    if clip.end_frame > max_frame:
                        max_frame = clip.end_frame
                    clips_info.append(
                        {
                            "clip_id": clip.clip_id,
                            "name": clip.name,
                            "start_frame": clip.start_frame,
                            "end_frame": clip.end_frame,
                            "start_timecode": self.frame_to_timecode(clip.start_frame),
                            "end_timecode": self.frame_to_timecode(clip.end_frame),
                            "duration_seconds": (clip.end_frame - clip.start_frame) / self.fps,
                            "has_mask": clip.mask_id is not None,
                            "has_tracking": clip.tracking_id is not None,
                        }
                    )
                tracks_info.append(
                    {
                        "track_id": track.track_id,
                        "track_index": track.track_index,
                        "track_name": track.track_name,
                        "clip_count": len(track.clips),
                        "clips": clips_info,
                    }
                )

            return {
                "playhead_timecode": self.frame_to_timecode(self.playhead_frame),
                "playhead_frame": self.playhead_frame,
                "fps": self.fps,
                "resolution": f"{self.width}x{self.height}",
                "total_duration_seconds": max_frame / self.fps if max_frame > 0 else 0.0,
                "tracks": tracks_info,
                "active_masks_count": len(self.masks),
                "active_motion_tracks_count": len(self.motion_tracks),
                "active_pip_composites_count": len(self.pip_composites),
            }

    def split_clip_at_timecode(self, track_id: str, clip_id: str, timecode: str) -> dict[str, Any]:
        """Splits a clip on a video track into two consecutive clips at the specified timecode."""
        with self._lock:
            if track_id not in self.tracks:
                raise KeyError(f"Track '{track_id}' not found. Available tracks: {list(self.tracks.keys())}")

            track = self.tracks[track_id]
            target_clip = next((c for c in track.clips if c.clip_id == clip_id), None)
            if not target_clip:
                raise KeyError(f"Clip '{clip_id}' not found on track '{track_id}'.")

            split_frame = self.timecode_to_frame(timecode)
            if not (target_clip.start_frame < split_frame < target_clip.end_frame):
                raise ValueError(
                    f"Split timecode '{timecode}' (frame {split_frame}) is outside clip boundaries "
                    f"[{self.frame_to_timecode(target_clip.start_frame)} .. {self.frame_to_timecode(target_clip.end_frame)}]."
                )

            self._save_snapshot()

            orig_end = target_clip.end_frame
            target_clip.end_frame = split_frame
            new_clip_a_id = target_clip.clip_id
            new_clip_b_id = f"{target_clip.clip_id}_part2_{uuid.uuid4().hex[:4]}"

            clip_b = MockClip(
                clip_id=new_clip_b_id,
                name=f"{target_clip.name} (Part 2)",
                start_frame=split_frame,
                end_frame=orig_end,
                source_duration_frames=target_clip.source_duration_frames,
                media_path=target_clip.media_path,
                transform=copy.deepcopy(target_clip.transform),
            )

            # Insert clip_b immediately after target_clip
            idx = track.clips.index(target_clip)
            track.clips.insert(idx + 1, clip_b)

            return {
                "status": "success",
                "track_id": track_id,
                "original_clip_id": clip_id,
                "new_clip_id_a": new_clip_a_id,
                "new_clip_id_b": new_clip_b_id,
                "split_frame": split_frame,
                "split_timecode": timecode,
                "clip_a_duration_seconds": (target_clip.end_frame - target_clip.start_frame) / self.fps,
                "clip_b_duration_seconds": (clip_b.end_frame - clip_b.start_frame) / self.fps,
            }

    def undo_last_timeline_action(self) -> dict[str, Any]:
        """Restores the last state snapshot from the undo stack."""
        with self._lock:
            if not self.undo_stack:
                return {"status": "no_op", "message": "Undo stack is empty. No previous actions to revert."}

            previous_state = self.undo_stack.pop()
            self.playhead_frame = previous_state["playhead_frame"]
            self.tracks = previous_state["tracks"]
            self.masks = previous_state["masks"]
            self.motion_tracks = previous_state["motion_tracks"]
            self.pip_composites = previous_state["pip_composites"]

            return {
                "status": "success",
                "message": "Successfully reverted to the previous timeline snapshot.",
                "remaining_undo_steps": len(self.undo_stack),
                "track_count": len(self.tracks),
            }

    def track_character_motion_keyframes(
        self,
        track_id: str,
        clip_id: str,
        target_label: str,
        start_timecode: str,
        end_timecode: str,
        sample_interval_frames: int = 1,
    ) -> dict[str, Any]:
        """Simulates 2D character motion tracking generating keyframe vectors."""
        with self._lock:
            if track_id not in self.tracks:
                raise KeyError(f"Track '{track_id}' not found.")
            track = self.tracks[track_id]
            clip = next((c for c in track.clips if c.clip_id == clip_id), None)
            if not clip:
                raise KeyError(f"Clip '{clip_id}' not found on track '{track_id}'.")

            start_f = self.timecode_to_frame(start_timecode)
            end_f = self.timecode_to_frame(end_timecode)
            if start_f >= end_f:
                raise ValueError(f"Start timecode '{start_timecode}' must be before end timecode '{end_timecode}'.")

            self._save_snapshot()

            # Generate mocked sinusoidal / smooth character motion keyframes
            keyframes: list[KeyframeVector] = []
            tracking_id = f"track_{uuid.uuid4().hex[:6]}"
            total_frames = end_f - start_f

            for f in range(start_f, end_f, max(1, sample_interval_frames)):
                progress = (f - start_f) / max(1, total_frames)
                # Smooth simulated movement from center-left to center-right with gentle bounce
                x = round(0.35 + 0.30 * progress, 4)
                y = round(0.50 + 0.05 * (progress * 3.14159), 4)
                scale = round(1.0 + 0.1 * progress, 4)
                rotation = round(-2.0 + 4.0 * progress, 2)
                keyframes.append(KeyframeVector(frame=f, x=x, y=y, scale=scale, rotation=rotation))

            motion_track = MockMotionTrack(
                tracking_id=tracking_id,
                clip_id=clip_id,
                target_label=target_label,
                start_frame=start_f,
                end_frame=end_f,
                keyframes=keyframes,
            )
            self.motion_tracks[tracking_id] = motion_track
            clip.tracking_id = tracking_id

            return {
                "status": "success",
                "tracking_id": tracking_id,
                "target_label": target_label,
                "clip_id": clip_id,
                "frame_count": len(keyframes),
                "start_timecode": start_timecode,
                "end_timecode": end_timecode,
                "keyframes_summary": f"Generated {len(keyframes)} keyframes for '{target_label}' with trajectory bounds [X: 0.35..0.65, Y: 0.50..0.55].",
            }

    def create_foreground_rotoscope_mask(
        self,
        track_id: str,
        clip_id: str,
        tracking_id: str | None = None,
        mask_shape: str = "silhouette",
        feather_pixels: float = 2.0,
        invert: bool = False,
    ) -> dict[str, Any]:
        """Generates a mocked foreground rotoscope alpha matte isolating character."""
        with self._lock:
            if track_id not in self.tracks:
                raise KeyError(f"Track '{track_id}' not found.")
            track = self.tracks[track_id]
            clip = next((c for c in track.clips if c.clip_id == clip_id), None)
            if not clip:
                raise KeyError(f"Clip '{clip_id}' not found on track '{track_id}'.")

            if tracking_id and tracking_id not in self.motion_tracks:
                raise KeyError(f"Motion tracking ID '{tracking_id}' does not exist.")

            self._save_snapshot()

            mask_id = f"mask_{uuid.uuid4().hex[:6]}"
            mask = MockRotoscopeMask(
                mask_id=mask_id,
                clip_id=clip_id,
                mask_shape=mask_shape,
                feather_pixels=feather_pixels,
                invert=invert,
                created_at_frame=self.playhead_frame,
            )
            self.masks[mask_id] = mask
            clip.mask_id = mask_id

            return {
                "status": "success",
                "mask_id": mask_id,
                "clip_id": clip_id,
                "mask_shape": mask_shape,
                "feather_pixels": feather_pixels,
                "invert": invert,
                "tracking_linked": tracking_id is not None,
                "alpha_matte_type": "RGBA_ALPHAMATTE_8BIT",
            }

    def pin_character_overlay_to_track(
        self,
        target_track_id: str,
        overlay_asset_id: str,
        tracking_id: str,
        mask_id: str | None = None,
        blend_mode: str = "normal",
        opacity: float = 1.0,
    ) -> dict[str, Any]:
        """Pins a cutout or graphics asset to a tracked character trajectory."""
        with self._lock:
            if target_track_id not in self.tracks:
                raise KeyError(f"Target track '{target_track_id}' does not exist.")
            if tracking_id not in self.motion_tracks:
                raise KeyError(f"Motion tracking ID '{tracking_id}' does not exist.")
            if mask_id and mask_id not in self.masks:
                raise KeyError(f"Rotoscope mask ID '{mask_id}' does not exist.")

            self._save_snapshot()

            motion = self.motion_tracks[tracking_id]
            target_track = self.tracks[target_track_id]

            composite_clip_id = f"overlay_{uuid.uuid4().hex[:6]}"
            new_clip = MockClip(
                clip_id=composite_clip_id,
                name=f"Overlay: {overlay_asset_id}",
                start_frame=motion.start_frame,
                end_frame=motion.end_frame,
                source_duration_frames=motion.end_frame - motion.start_frame,
                mask_id=mask_id,
                tracking_id=tracking_id,
            )
            target_track.clips.append(new_clip)

            return {
                "status": "success",
                "composite_clip_id": composite_clip_id,
                "target_track_id": target_track_id,
                "overlay_asset_id": overlay_asset_id,
                "tracking_id": tracking_id,
                "keyframes_attached": len(motion.keyframes),
                "blend_mode": blend_mode,
                "opacity": opacity,
            }

    def create_masked_picture_in_picture(
        self,
        base_track_id: str,
        pip_track_id: str,
        pip_clip_id: str,
        position: str = "top-right",
        normalized_x: float = 0.75,
        normalized_y: float = 0.75,
        scale: float = 0.28,
        mask_shape: str = "rounded_rect",
        border_width: int = 4,
        border_color: str = "#FFFFFF",
    ) -> dict[str, Any]:
        """Constructs a Picture-in-Picture composite on an upper track with a mask shape."""
        with self._lock:
            if base_track_id not in self.tracks:
                raise KeyError(f"Base track '{base_track_id}' not found.")
            if pip_track_id not in self.tracks:
                raise KeyError(f"PiP track '{pip_track_id}' not found.")

            base_track = self.tracks[base_track_id]
            pip_track = self.tracks[pip_track_id]

            if pip_track.track_index <= base_track.track_index:
                raise ValueError(
                    f"PiP track '{pip_track_id}' (index {pip_track.track_index}) must be positioned above "
                    f"base track '{base_track_id}' (index {base_track.track_index}) in timeline layer hierarchy."
                )

            pip_clip = next((c for c in pip_track.clips if c.clip_id == pip_clip_id), None)
            if not pip_clip:
                raise KeyError(f"PiP clip '{pip_clip_id}' not found on track '{pip_track_id}'.")

            if not (0.0 <= normalized_x <= 1.0 and 0.0 <= normalized_y <= 1.0):
                raise ValueError(f"Normalized coordinates (x={normalized_x}, y={normalized_y}) must be in range [0.0, 1.0].")

            self._save_snapshot()

            pip_id = f"pip_{uuid.uuid4().hex[:6]}"
            pip_composite = MockPiPComposite(
                pip_id=pip_id,
                base_track_id=base_track_id,
                pip_track_id=pip_track_id,
                pip_clip_id=pip_clip_id,
                position=position,
                normalized_x=normalized_x,
                normalized_y=normalized_y,
                scale=scale,
                mask_shape=mask_shape,
                border_width=border_width,
                border_color=border_color,
            )
            self.pip_composites[pip_id] = pip_composite
            pip_clip.transform = {"x": normalized_x, "y": normalized_y, "scale": scale, "rotation": 0.0}

            return {
                "status": "success",
                "pip_id": pip_id,
                "base_track_id": base_track_id,
                "pip_track_id": pip_track_id,
                "pip_clip_id": pip_clip_id,
                "position_preset": position,
                "coordinates": {"x": normalized_x, "y": normalized_y, "scale": scale},
                "mask_shape": mask_shape,
                "border": f"{border_width}px {border_color}",
            }

    def render_mock_composite_export(
        self,
        output_format: str = "mp4",
        resolution: str = "1920x1080",
        fps: float = 24.0,
        render_preset: str = "ProRes_422",
    ) -> dict[str, Any]:
        """Simulates rendering and exporting the final composite timeline."""
        with self._lock:
            render_job_id = f"render_{uuid.uuid4().hex[:8]}"
            export_path = f"mock://exports/final_cut_{render_job_id}.{output_format}"

            total_clips = sum(len(t.clips) for t in self.tracks.values())
            simulated_seconds = round(0.5 + 0.1 * total_clips + 0.2 * len(self.pip_composites), 2)

            return {
                "status": "success",
                "render_job_id": render_job_id,
                "export_path": export_path,
                "resolution": resolution,
                "fps": fps,
                "format": output_format,
                "preset": render_preset,
                "tracks_rendered": len(self.tracks),
                "total_clips": total_clips,
                "pip_composites_applied": len(self.pip_composites),
                "masks_applied": len(self.masks),
                "simulated_render_time_seconds": simulated_seconds,
            }
