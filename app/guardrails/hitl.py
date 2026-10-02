"""Human-in-the-Loop (HITL) confirmation gate for high-stakes editing operations."""

from __future__ import annotations

import threading
import uuid
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# High-stakes tools requiring explicit human confirmation
HIGH_STAKES_OPERATIONS: set[str] = {
    "render_mock_composite_export",
    "delete_timeline_track",
    "purge_all_clips",
}


class HITLApprovalGate:
    """Thread-safe Human-in-the-Loop confirmation gate."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending_approvals: dict[str, dict[str, Any]] = {}
        self._approved_tokens: set[str] = set()

    def requires_approval(self, tool_name: str) -> bool:
        """Determines if a tool requires explicit human approval before execution."""
        return tool_name in HIGH_STAKES_OPERATIONS

    def create_approval_request(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        session_id: str = "default_session",
    ) -> dict[str, Any]:
        """Creates a pending approval request and returns the review challenge."""
        with self._lock:
            approval_token = f"hitl_tok_{uuid.uuid4().hex[:8]}"
            payload = {
                "approval_token": approval_token,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "session_id": session_id,
                "status": "PENDING_APPROVAL",
            }
            self._pending_approvals[approval_token] = payload
            logger.info("HITL approval required for high-stakes action", tool_name=tool_name, approval_token=approval_token)
            return {
                "status": "PENDING_HUMAN_APPROVAL",
                "approval_token": approval_token,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "message": f"Action '{tool_name}' is classified as HIGH-STAKES and requires explicit human confirmation.",
                "recovery_instructions": f"Ask the user for explicit confirmation. To execute, pass 'approval_token': '{approval_token}' in the tool parameters.",
            }

    def verify_or_challenge(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        session_id: str = "default_session",
    ) -> dict[str, Any] | None:
        """If tool is high-stakes and token is missing or not approved, returns approval challenge."""
        if not self.requires_approval(tool_name):
            return None

        token = tool_args.get("approval_token")
        with self._lock:
            if token and token in self._approved_tokens:
                # Token is authorized - consume and allow
                self._approved_tokens.remove(token)
                logger.info("HITL token validated; proceeding with high-stakes tool", tool_name=tool_name, token=token)
                return None

        # Challenge needed
        return self.create_approval_request(tool_name, tool_args, session_id)

    def approve(self, approval_token: str) -> bool:
        """Grants human approval for a pending token."""
        with self._lock:
            if approval_token in self._pending_approvals:
                self._pending_approvals[approval_token]["status"] = "APPROVED"
                self._approved_tokens.add(approval_token)
                logger.info("HITL token approved by user", approval_token=approval_token)
                return True
            return False

    def reject(self, approval_token: str) -> bool:
        """Denies approval for a pending token."""
        with self._lock:
            if approval_token in self._pending_approvals:
                self._pending_approvals[approval_token]["status"] = "REJECTED"
                self._pending_approvals.pop(approval_token, None)
                logger.info("HITL token rejected by user", approval_token=approval_token)
                return True
            return False


# Global approval gate instance
approval_gate = HITLApprovalGate()
