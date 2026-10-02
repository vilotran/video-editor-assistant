# Agent Spec: Mocked VFX & Video Editing Agent (NLE Co-Pilot)

## Overview
An intelligent, multi-agent conversational VFX and video editing assistant operating on an internal, fully mocked timeline and compositing engine (`MockVideoEditorEngine`). The system empowers users to perform complex, multi-layered video editing and visual effects operations—such as precision timeline cuts, character motion tracking, rotoscope foreground masking, keyframe-pinned character overlays, and masked Picture-in-Picture (PiP)—using natural language.

The architecture strictly adheres to all 19 criteria across the 5 categories of the AgentOps Assessment Matrix (95/95 points), incorporating multi-agent coordination, strategic model routing (`gemini-2.5-pro` and `gemini-2.5-flash`), persistent SQLite session state, async memory consolidation, OpenTelemetry distributed tracing, Cloud DLP PII redaction, ADK guardrails, Human-in-the-Loop (HITL) approval gates, Terraform IaC, and automated evaluation suites.

## Language
`python` (Python 3.12+, `google.adk` / `agents-cli`)

---

## Architecture & Multi-Agent Sub-Agents
The system implements an ADK Multi-Agent Coordinator-Specialist topology with strategic model routing:

1. **`DirectorAgent` (Coordinator / Supervisor)**
   - **Model**: `gemini-2.5-pro` (optimized for complex multi-turn reasoning, plan synthesis, and context understanding).
   - **Role**: Conversational interface with the user. Decomposes high-level creative requests (e.g., "Track the skater's face, mask them out, and add a blurred PiP overlay in the top right") into structured sub-tasks. Routes tasks to specialist sub-agents, synthesizes their results, and provides clear user feedback. Enforces HITL approval gates.

2. **`TimelineAgent` (Timeline & Cut Specialist)**
   - **Model**: `gemini-2.5-flash` (optimized for ultra-fast, deterministic tool calling and low latency).
   - **Role**: Manages timeline structure across mocked video tracks (V1, V2, V3...), clips, timecode math, splitting/cutting, and snapshot restoration (undo).

3. **`MaskAndTrackAgent` (Motion Tracking & Masking Specialist)**
   - **Model**: `gemini-2.5-flash` (fast, deterministic tool calling).
   - **Role**: Analyzes character motion, calculates mocked frame-by-frame `(frame, x, y, scale, rotation)` motion keyframes, and generates foreground rotoscope alpha masks.

4. **`VFXCompositorAgent` (Compositing & Special Effects Specialist)**
   - **Model**: `gemini-2.5-flash` (fast, deterministic tool calling).
   - **Role**: Handles multi-track spatial compositing, pinning character cutouts to motion tracks, configuring masked Picture-in-Picture (PiP) overlays, and triggering export rendering after confirmation.

---

## Mocked Video Editor Engine & Tools Required

All tools operate on a thread-safe, persistent `MockVideoEditorEngine` simulating multi-track video timeline operations. Every tool is defined with comprehensive docstrings, explicit Pydantic `BaseModel` schemas for inputs and outputs, and guided error handling returning structured recovery instructions.

### 1. `TimelineAgent` Tools
* **`get_timeline_state`**:
  - *Description*: Inspects and returns the full current state of mocked timeline tracks (V1, V2, V3, etc.), active playhead timecode, clip metadata (in/out points, duration, source resolution), and timeline FPS.
  - *Input Schema*: `GetTimelineStateInput(track_filter: Optional[List[str]])`
  - *Output Schema*: `GetTimelineStateOutput(tracks: List[TrackState], playhead_timecode: str, fps: float, total_duration_seconds: float)`
* **`split_clip_at_timecode`**:
  - *Description*: Performs a razor cut / split on a specified clip on a video track at the given timecode string (`HH:MM:SS:FF` or seconds).
  - *Input Schema*: `SplitClipInput(track_id: str, clip_id: str, timecode: str)`
  - *Output Schema*: `SplitClipOutput(original_clip_id: str, new_clip_id_a: str, new_clip_id_b: str, split_timecode: str, status: str)`
* **`undo_last_timeline_action`**:
  - *Description*: Restores the timeline state to the previous snapshot from the undo stack.
  - *Input Schema*: `UndoTimelineActionInput()`
  - *Output Schema*: `UndoTimelineActionOutput(restored_snapshot_id: str, message: str, current_track_count: int)`

### 2. `MaskAndTrackAgent` Tools
* **`track_character_motion_keyframes`**:
  - *Description*: Generates mocked 2D motion tracking keyframe vectors `(frame, x, y, scale, rotation)` for a target face or moving character across a clip's frame range.
  - *Input Schema*: `TrackMotionInput(track_id: str, clip_id: str, target_label: str, start_timecode: str, end_timecode: str, sample_interval_frames: int = 1)`
  - *Output Schema*: `TrackMotionOutput(tracking_id: str, target_label: str, frame_count: int, keyframes: List[KeyframeVector], summary: str)`
* **`create_foreground_rotoscope_mask`**:
  - *Description*: Generates a mocked foreground rotoscope alpha matte isolating a moving character, face, or object with customizable edge feathering and inversion options.
  - *Input Schema*: `RotoscopeMaskInput(track_id: str, clip_id: str, tracking_id: Optional[str], mask_shape: str, feather_pixels: float = 2.0, invert: bool = False)`
  - *Output Schema*: `RotoscopeMaskOutput(mask_id: str, clip_id: str, mask_shape: str, alpha_channels: int, status: str)`

### 3. `VFXCompositorAgent` Tools
* **`pin_character_overlay_to_track`**:
  - *Description*: Attaches and transforms a mocked overlay image or character cutout onto a tracked character or face using previously computed motion keyframes and an optional rotoscope mask.
  - *Input Schema*: `PinOverlayInput(target_track_id: str, overlay_asset_id: str, tracking_id: str, mask_id: Optional[str], blend_mode: str = "normal", opacity: float = 1.0)`
  - *Output Schema*: `PinOverlayOutput(composite_id: str, overlay_track_id: str, status: str, keyframes_applied: int)`
* **`create_masked_picture_in_picture`**:
  - *Description*: Constructs a Picture-in-Picture (PiP) composite by placing a secondary video clip on an upper track over a primary background track, masked by a designated shape (circle, rounded_rect, silhouette) with defined normalized position coordinates (`x`, `y`) and scale.
  - *Input Schema*: `MaskedPiPInput(base_track_id: str, pip_track_id: str, pip_clip_id: str, position: str, normalized_x: float, normalized_y: float, scale: float, mask_shape: str, border_width: int = 0, border_color: str = "#FFFFFF")`
  - *Output Schema*: `MaskedPiPOutput(pip_id: str, pip_track_id: str, base_track_id: str, final_coordinates: Dict[str, float], status: str)`
* **`render_mock_composite_export`**:
  - *Description*: Simulates the final high-resolution timeline export and video rendering. Marked as a high-stakes action that triggers a Human-in-the-Loop (HITL) approval gate before execution.
  - *Input Schema*: `RenderExportInput(output_format: str = "mp4", resolution: str = "1920x1080", fps: float = 24.0, render_preset: str = "ProRes_422")`
  - *Output Schema*: `RenderExportOutput(render_job_id: str, export_path: str, simulated_render_time_seconds: float, status: str)`

---

## 19 Grading Rubric Requirements (95/95 Points Matrix)

| Category (20/15 pts) | Rubric Item (5 pts each) | Implementation in Mocked VFX Video Editing Agent |
|---|---|---|
| **1. Tool & Interface Design (20 pts)** | **1. Comprehensive Tool Docstrings** | Every tool includes complete Google-style docstrings documenting operational semantics, pre-conditions, all arguments, and return types. |
| | **2. Descriptive Naming** | Tool names follow explicit verb-noun conventions (`track_character_motion_keyframes`, `create_foreground_rotoscope_mask`, `create_masked_picture_in_picture`, `pin_character_overlay_to_track`). |
| | **3. Explicit JSON Schemas** | All tool inputs and outputs are defined with strict Pydantic `BaseModel` classes with field constraints (`Field(ge=0.0, le=1.0)`), typed enums, and comprehensive field descriptions. |
| | **4. Guided Error Handling** | Mock tools catch errors (e.g. invalid timecodes, missing tracks, out-of-bounds coordinates) and return structured dictionaries with `error_code`, `message`, and `recovery_instructions` guiding the LLM on which tool to call next, avoiding unhandled exceptions. |
| **2. Context & Memory (20 pts)** | **5. Robust System Instructions** | System prompts define a strict "Constitution" specifying agent persona, timeline layering hierarchy (V1 background, V2 PiP, V3 graphics), compositing rules, and tone. |
| | **6. History Compaction** | Implements token-aware sliding window compaction, conversation summarization, and keyframe array compaction (summarizing 240+ raw keyframe points into trajectory bounds). |
| | **7. Persistent Session State** | Persistent state storage using `sqlite3` (`timeline_state`, `sessions`, `undo_snapshots`, `vfx_presets`) paired with a local vector indexing interface for semantic recall of past project configurations. |
| | **8. Async Memory Operations** | Background `asyncio.create_task` handlers execute memory consolidation, session checkpointing, and user preference extraction without blocking the interactive UI turn. |
| **3. Orchestration & Logic (20 pts)** | **9. Multi-Agent Patterns** | Hierarchical ADK Multi-Agent architecture: `DirectorAgent` (Coordinator) delegating to `TimelineAgent`, `MaskAndTrackAgent`, and `VFXCompositorAgent`. |
| | **10. Strategic Model Routing** | `DirectorAgent` runs on `gemini-2.5-pro` (advanced multi-step planning); sub-agents (`TimelineAgent`, `MaskAndTrackAgent`, `VFXCompositorAgent`) run on `gemini-2.5-flash` (fast tool calling). |
| | **11. Guardrails & Policy Plugins** | ADK `BasePlugin` / callbacks inspect input prompts for safety/injections, validate timecode syntax and track bounds, and run self-evaluation checks on proposed composite plans. |
| | **12. Human-in-the-Loop (HITL) Hooks** | Explicit confirmation hook pauses destructive actions (track deletion) and high-stakes operations (`render_mock_composite_export`) awaiting explicit human sign-off (`APPROVED`/`REJECTED`). |
| **4. Observability & Tracing (20 pts)** | **13. Structured JSON Logging** | Standardized JSON logging using `structlog` / `python-json-logger`, producing ISO-8601 timestamps, log levels, correlation IDs, and context dicts (zero raw `print()` statements). |
| | **14. Intent vs. Outcome Capture** | Dedicated logging middleware emitting an `INTENT` event before tool dispatch and a paired `OUTCOME` event with execution metrics and status upon tool completion. |
| | **15. Distributed Tracing** | OpenTelemetry (`TracerProvider`, `BatchSpanProcessor`, OpenTelemetry Google Cloud Trace exporter) generating nested spans: `turn_span` -> `director_span` -> `subagent_span` -> `tool_span`. |
| | **16. PII Redaction** | Data scrubbing filter combining Google Cloud DLP API client interface with regex masking (emails, API keys, phone numbers, person names) before persisting to logs or SQLite memory. |
| **5. Infrastructure & CI/CD (15 pts)** | **17. Automated Evaluation Suites** | Automated testing harness using `pytest` for unit/integration tests and an ADK `AgentEvaluator` with golden eval datasets (`eval/eval_dataset.jsonl`) testing multi-turn editing trajectories. |
| | **18. Infrastructure as Code (IaC)** | Production-ready `terraform/` directory (`main.tf`, `variables.tf`, `outputs.tf`) provisioning Cloud Run, Artifact Registry, Secret Manager, and Cloud Trace; fully documented in `README.md`. |
| | **19. Secure Secret Management** | Google Cloud Secret Manager client (`SecretManagerServiceClient`) fetching API keys and project settings dynamically with local `.env` fallback and zero hardcoded credentials. |

---

## Constraints & Safety Rules
1. **No Destructive Action Without Confirmation**: High-stakes operations (`render_mock_composite_export`, wiping tracks) require an affirmative human confirmation token before execution.
2. **Layering Integrity**: PiP overlays and character overlays must strictly reside on tracks with an index higher than the underlying base clip (e.g., overlay on V2/V3, base on V1).
3. **Timecode & Coordinate Validation**: Timecodes must adhere to standard SMPTE or numeric seconds within clip duration. PiP coordinates must normalize to `0.0 <= x, y <= 1.0`.
4. **PII Sanitization**: All log entries and session records must pass through the redaction pipeline prior to output.

---

## Success Criteria
- **100% Score on AgentOps Assessment**: All 19 criteria satisfied with verified code implementations.
- **Eval Benchmark**: Golden evaluation dataset (`eval/eval_dataset.jsonl`) runs against ADK `AgentEvaluator` with >= 90% trajectory accuracy on multi-step VFX workflows.
- **Test Suite**: Automated `pytest` suite covering unit tests for mock engine, Pydantic schemas, guided error handling, and multi-agent coordination passes with 100% success.
- **CI/CD Quality**: GitHub Actions workflow runs linting (`ruff`), typing (`mypy`), unit tests, and eval harness cleanly on every push.

---

## Reference Samples
- `core/python/long-horizon-harness`: Multi-agent delegation, layered tool guardrails, session state persistence, and HITL approval gates.
- `core/python/safety-plugins`: Runner-wide safety guardrails, input validation, and moderation callbacks.
- `core/python/cross-session-memory`: Persistent SQLite and vector state management across turns and sessions.
