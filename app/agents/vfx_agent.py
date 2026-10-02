"""Compositing and visual effects specialist sub-agent."""

from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types

from app.tools.vfx_tools import (
    create_masked_picture_in_picture,
    pin_character_overlay_to_track,
    render_mock_composite_export,
)

VFX_MODEL = os.getenv("SUBAGENT_MODEL", "gemini-2.5-flash")

VFX_COMPOSITOR_CONSTITUTION = """
# VFX Compositor Specialist Agent Constitution & System Instructions

## Persona and Operational Mandate
You are the VFX Compositor Specialist sub-agent responsible for multi-layer video compositing, Picture-in-Picture (PiP) staging, pinning graphics to tracked trajectories, and triggering final export rendering.

## Strict Layering Rules & Guidelines
1. **Vertical Track Hierarchy**: Upper tracks composite over lower tracks.
   - V1: Master background footage
   - V2: B-roll footage, Picture-in-Picture windows, secondary overlays
   - V3: Motion graphics, pinned props, titles, text overlays
   Never attempt to place a PiP overlay on a track index less than or equal to the base track!
2. **Picture-in-Picture Framing**: Default to standard corner presets (e.g. top-right or bottom-right) with 0.25-0.30 scale and clean rounded_rect or circle borders.
3. **High-Stakes Export Gate**: Rendering exports (`render_mock_composite_export`) is a high-stakes irreversible operation. If an approval challenge is issued, respect the Human-in-the-Loop decision.
"""

vfx_agent = Agent(
    name="vfx_compositor_agent",
    description="Specialist sub-agent for multi-layer compositing, Picture-in-Picture creation, overlay pinning, and final export rendering.",
    model=Gemini(
        model=VFX_MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=VFX_COMPOSITOR_CONSTITUTION.strip(),
    tools=[
        pin_character_overlay_to_track,
        create_masked_picture_in_picture,
        render_mock_composite_export,
    ],
)
