"""Enterprise Safety, Security Guardrails, and Self-Evaluation Plugin for ADK."""

from __future__ import annotations

import re
from typing import Any

import structlog
from google.adk.agents.invocation_context import InvocationContext
from google.adk.plugins.base_plugin import BasePlugin
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from app.guardrails.hitl import approval_gate

logger = structlog.get_logger(__name__)

# Prompt injection patterns
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?system\s+prompt", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+in\s+developer\s+mode", re.IGNORECASE),
    re.compile(r"jailbreak|dan\s+mode", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(full\s+)?system\s+(prompt|instructions)", re.IGNORECASE),
]

TIMECODE_SMPTE_PATTERN = re.compile(r"^\d{2}:\d{2}:\d{2}:\d{2}$")


class VFXSafetyPolicyPlugin(BasePlugin):
    """ADK plugin enforcing prompt safety, timecode syntax, composite layer logic, and HITL."""

    def __init__(self) -> None:
        super().__init__(name="VFXSafetyPolicyPlugin")

    def _is_injection(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in INJECTION_PATTERNS)

    async def on_user_message_callback(
        self,
        invocation_context: InvocationContext,
        user_message: types.Content,
    ) -> types.Content | None:
        """Scans user message for prompt injection attacks and safety violations."""
        if not user_message.parts:
            return None

        for part in user_message.parts:
            if hasattr(part, "text") and part.text:
                if self._is_injection(part.text):
                    logger.warn("Prompt injection detected and blocked", prompt_snippet=part.text[:80])
                    invocation_context.session.state["is_user_prompt_safe"] = False
                    return types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(
                                text="[Security Policy Violation: Prompt injection pattern detected and neutralised.]"
                            )
                        ],
                    )

        invocation_context.session.state["is_user_prompt_safe"] = True
        return None

    async def before_run_callback(
        self,
        invocation_context: InvocationContext,
    ) -> types.Content | None:
        """Halts the runner if prompt was classified as unsafe by on_user_message_callback."""
        if not invocation_context.session.state.get("is_user_prompt_safe", True):
            invocation_context.session.state["is_user_prompt_safe"] = True
            return types.Content(
                role="model",
                parts=[
                    types.Part.from_text(
                        text="I cannot fulfill this request as it violates system security policy constraints."
                    )
                ],
            )
        return None

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> dict[str, Any] | None:
        """Validates tool inputs, layer hierarchy constraints, and checks HITL approval."""
        tool_name = getattr(tool, "name", str(tool))

        # 1. Human-in-the-Loop check
        if approval_gate.requires_approval(tool_name):
            challenge = approval_gate.verify_or_challenge(tool_name, tool_args)
            if challenge:
                logger.info("Halting high-stakes tool execution for HITL approval", tool_name=tool_name)
                return challenge

        # 2. Timecode syntax verification guardrail
        timecode = tool_args.get("timecode") or tool_args.get("start_timecode")
        if timecode and isinstance(timecode, str):
            # SMPTE HH:MM:SS:FF or numeric seconds
            if not (TIMECODE_SMPTE_PATTERN.match(timecode) or timecode.replace(".", "", 1).isdigit()):
                logger.warn("Invalid timecode syntax intercepted by guardrail", timecode=timecode)
                return {
                    "is_error": True,
                    "error_code": "GUARDRAIL_INVALID_TIMECODE_SYNTAX",
                    "message": f"Timecode '{timecode}' violates SMPTE HH:MM:SS:FF formatting standards.",
                    "recovery_instructions": "Format timecodes as 'HH:MM:SS:FF' (e.g. '00:00:15:00') or float seconds (e.g. '15.0').",
                }

        # 3. Composite layer hierarchy self-evaluation
        if tool_name == "create_masked_picture_in_picture":
            base_t = tool_args.get("base_track_id", "")
            pip_t = tool_args.get("pip_track_id", "")
            if base_t and pip_t:
                # V1 = index 1, V2 = index 2, V3 = index 3
                def get_idx(t_id: str) -> int:
                    m = re.search(r"\d+", t_id)
                    return int(m.group(0)) if m else 0

                if get_idx(pip_t) <= get_idx(base_t):
                    logger.warn("Invalid composite layer hierarchy intercepted", base_track=base_t, pip_track=pip_t)
                    return {
                        "is_error": True,
                        "error_code": "GUARDRAIL_INVALID_LAYER_HIERARCHY",
                        "message": f"PiP track '{pip_t}' cannot be placed below or on same level as base track '{base_t}'.",
                        "recovery_instructions": "Select an upper track for PiP (e.g. base_track_id='V1', pip_track_id='V2' or 'V3').",
                    }

        return None
