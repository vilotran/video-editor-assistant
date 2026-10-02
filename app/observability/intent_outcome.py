"""Explicit INTENT vs OUTCOME event logger for tool execution auditing."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import structlog

from app.observability.logging import app_logger

logger = structlog.get_logger("intent_outcome")


class IntentOutcomeAuditLogger:
    """Audits agent operational intent before dispatch and outcome upon completion."""

    @staticmethod
    def log_intent(
        correlation_id: str,
        agent_name: str,
        tool_name: str,
        arguments: dict[str, Any],
        intent_summary: str,
    ) -> float:
        """Emits structured INTENT log record prior to tool execution."""
        start_time = time.perf_counter()
        app_logger.info(
            "Tool execution intent declared",
            event_type="INTENT",
            correlation_id=correlation_id,
            agent_name=agent_name,
            tool_name=tool_name,
            tool_arguments=arguments,
            intent_summary=intent_summary,
        )
        return start_time

    @staticmethod
    def log_outcome(
        correlation_id: str,
        agent_name: str,
        tool_name: str,
        start_time: float,
        status: str,
        result: Any,
        error: str | None = None,
    ) -> None:
        """Emits structured OUTCOME log record following tool completion."""
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        app_logger.info(
            "Tool execution outcome recorded",
            event_type="OUTCOME",
            correlation_id=correlation_id,
            agent_name=agent_name,
            tool_name=tool_name,
            duration_ms=duration_ms,
            status=status,
            result_summary=str(result)[:300] if result else None,
            error=error,
        )


def audit_tool_call(agent_name: str, tool_name: str, intent_summary: str) -> Callable:
    """Decorator to automatically capture INTENT before and OUTCOME after a tool execution."""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            correlation_id = kwargs.get("correlation_id", "turn_corr_default")
            start_t = IntentOutcomeAuditLogger.log_intent(
                correlation_id=correlation_id,
                agent_name=agent_name,
                tool_name=tool_name,
                arguments=kwargs,
                intent_summary=intent_summary,
            )
            try:
                res = func(*args, **kwargs)
                status = "ERROR" if isinstance(res, dict) and res.get("is_error") else "SUCCESS"
                IntentOutcomeAuditLogger.log_outcome(
                    correlation_id=correlation_id,
                    agent_name=agent_name,
                    tool_name=tool_name,
                    start_time=start_t,
                    status=status,
                    result=res,
                )
                return res
            except Exception as exc:
                IntentOutcomeAuditLogger.log_outcome(
                    correlation_id=correlation_id,
                    agent_name=agent_name,
                    tool_name=tool_name,
                    start_time=start_t,
                    status="EXCEPTION",
                    result=None,
                    error=str(exc),
                )
                raise
        return wrapper
    return decorator
