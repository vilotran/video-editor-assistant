"""Timeline specialist sub-agent responsible for timeline inspection, razor splits, and undos."""

from __future__ import annotations

import os

from google.adk.agents import Agent
from google.adk.models import Gemini
from google.genai import types

from app.tools.timeline_tools import (
    get_timeline_state,
    split_clip_at_timecode,
    undo_last_timeline_action,
)

TIMELINE_MODEL = os.getenv("SUBAGENT_MODEL", "gemini-2.5-flash")

TIMELINE_CONSTITUTION = """
# Timeline Specialist Agent Constitution & System Instructions

## Persona and Operational Mandate
You are the Timeline Specialist sub-agent in an enterprise NLE (Non-Linear Editor) video editing suite.
Your sole domain of responsibility is managing the timeline tracks (V1, V2, V3), media clips, in/out cut boundaries, SMPTE timecode transformations, and timeline state history.

## Strict Operational Rules
1. **Always Inspect First**: When a user request references a clip or cut point without explicit clip IDs or track IDs, invoke `get_timeline_state()` first to examine the active tracks and clips.
2. **SMPTE Timecode Integrity**: Adhere strictly to SMPTE `HH:MM:SS:FF` format or valid positive seconds. Never attempt cuts outside clip in/out boundaries.
3. **Non-Destructive Workflows**: Use `undo_last_timeline_action()` immediately if a split operation was requested in error or if the user asks to revert changes.
4. **Structured Recovery**: If a tool returns a `ToolErrorResponse`, follow its `recovery_instructions` precisely rather than hallucinating IDs.
"""

timeline_agent = Agent(
    name="timeline_agent",
    description="Specialist sub-agent for inspecting timeline tracks, performing razor splits at timecodes, and undoing edits.",
    model=Gemini(
        model=TIMELINE_MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=TIMELINE_CONSTITUTION.strip(),
    tools=[
        get_timeline_state,
        split_clip_at_timecode,
        undo_last_timeline_action,
    ],
)
