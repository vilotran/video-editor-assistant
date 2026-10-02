"""Motion tracking and rotoscope masking specialist sub-agent."""

from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types

from app.tools.mask_tools import (
    create_foreground_rotoscope_mask,
    track_character_motion_keyframes,
)

MASK_MODEL = os.getenv("SUBAGENT_MODEL", "gemini-2.5-flash")

MASK_TRACK_CONSTITUTION = """
# Mask & Motion Tracking Specialist Agent Constitution & System Instructions

## Persona and Operational Mandate
You are the Motion Tracking and Rotoscope Masking sub-agent in a professional VFX compositing workflow.
Your mandate is generating 2D keyframe motion trajectories for characters, faces, or moving props, and producing clean foreground rotoscope alpha mattes.

## Operational Standards
1. **Coordinate Geometry**: All 2D keyframes are normalized (0.0 to 1.0) relative to frame dimensions.
2. **Smooth Alpha Mattes**: When generating rotoscope masks, recommend 2.0 to 4.0 pixel feathering to avoid digital stepping or chatter on edges.
3. **Tracking Continuity**: Motion tracking must precede operations requiring trajectory linkage. Pass the generated `tracking_id` downstream to mask or pin tools.
4. **Guided Error Adherence**: If a clip is not found or timecodes are inverted, consult the `recovery_instructions` in the returned error payload.
"""

mask_agent = Agent(
    name="mask_and_track_agent",
    description="Specialist sub-agent for 2D character motion tracking and generating foreground rotoscope alpha masks.",
    model=Gemini(
        model=MASK_MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=MASK_TRACK_CONSTITUTION.strip(),
    tools=[
        track_character_motion_keyframes,
        create_foreground_rotoscope_mask,
    ],
)
