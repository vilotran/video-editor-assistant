"""Asynchronous background memory operations and consolidation tasks."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.memory.session_store import session_store
from app.memory.vector_store import vector_store

logger = structlog.get_logger(__name__)


async def consolidate_session_memory_async(
    session_id: str,
    timeline_state: dict[str, Any],
    user_utterance: str | None = None,
    turn_index: int = 0,
) -> None:
    """Background async worker that consolidates session state and extracts preferences without blocking UI."""
    try:
        # 1. Non-blocking persist to SQLite
        session_store.save_session_state(
            session_id=session_id,
            state_dict=timeline_state,
            turn_index=turn_index,
        )

        if user_utterance:
            session_store.record_conversation_event(
                session_id=session_id,
                role="user",
                content=user_utterance,
            )

        # 2. Extract potential new preferences into vector store
        if user_utterance and ("prefer" in user_utterance.lower() or "always" in user_utterance.lower()):
            vector_store.add_document(
                doc_id=f"pref_{session_id}_{turn_index}",
                title="User Custom Editing Preference",
                content=user_utterance,
                metadata={"session_id": session_id, "type": "learned_preference"},
            )
            logger.info("Learned user preference indexed into vector store", session_id=session_id)

        logger.debug("Async memory consolidation completed", session_id=session_id, turn_index=turn_index)
    except Exception as exc:
        logger.error("Async memory consolidation failed", session_id=session_id, error=str(exc))


def dispatch_async_memory_consolidation(
    session_id: str,
    timeline_state: dict[str, Any],
    user_utterance: str | None = None,
    turn_index: int = 0,
) -> asyncio.Task | None:
    """Schedules consolidate_session_memory_async as a non-blocking background task."""
    try:
        loop = asyncio.get_running_loop()
        return loop.create_task(
            consolidate_session_memory_async(
                session_id=session_id,
                timeline_state=timeline_state,
                user_utterance=user_utterance,
                turn_index=turn_index,
            )
        )
    except RuntimeError:
        # If no active event loop in current thread, run synchronously or via background thread
        asyncio.run(
            consolidate_session_memory_async(
                session_id=session_id,
                timeline_state=timeline_state,
                user_utterance=user_utterance,
                turn_index=turn_index,
            )
        )
        return None
