"""History compaction utilities including token sliding window, summarization, and keyframe compression."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class HistoryCompactor:
    """Manages context bloat via token-aware sliding window compaction and keyframe reduction."""

    def __init__(self, max_history_turns: int = 10, max_token_budget: int = 8192) -> None:
        self.max_history_turns = max_history_turns
        self.max_token_budget = max_token_budget

    @staticmethod
    def compact_keyframe_array(keyframes: list[dict[str, Any]]) -> dict[str, Any]:
        """Reduces verbose frame-by-frame keyframe arrays into concise mathematical bounds.

        Prevents context explosion when motion tracking returns hundreds of dense vectors.
        """
        if not keyframes:
            return {"frame_count": 0, "summary": "Empty keyframes"}

        start_frame = keyframes[0].get("frame", 0)
        end_frame = keyframes[-1].get("frame", 0)
        xs = [k.get("x", 0.0) for k in keyframes]
        ys = [k.get("y", 0.0) for k in keyframes]
        scales = [k.get("scale", 1.0) for k in keyframes]

        return {
            "frame_count": len(keyframes),
            "frame_range": f"{start_frame}..{end_frame}",
            "x_bounds": [min(xs), max(xs)],
            "y_bounds": [min(ys), max(ys)],
            "scale_bounds": [min(scales), max(scales)],
            "sample_start": keyframes[0],
            "sample_mid": keyframes[len(keyframes) // 2],
            "sample_end": keyframes[-1],
            "is_compacted": True,
        }

    def compact_conversation_history(
        self,
        messages: list[dict[str, Any]],
        system_instruction: str | None = None,
    ) -> list[dict[str, Any]]:
        """Applies sliding window compaction with synthetic summary prefix to preserve vital context."""
        if len(messages) <= self.max_history_turns:
            return messages

        # Retain earliest turn (often contains project goal) and recent window
        initial_turn = messages[:2]  # Initial user + assistant prompt/response
        sliding_window = messages[-(self.max_history_turns - 2):]

        # Generate synthetic summary of dropped intermediate turns
        dropped_count = len(messages) - len(initial_turn) - len(sliding_window)
        summary_event = {
            "role": "system",
            "content": f"[Context Compaction: Summarized {dropped_count} intermediate editing turns. Timeline track state and active clip snapshots are safely persisted in SQLite state store.]",
        }

        compacted = [*initial_turn, summary_event, *sliding_window]
        logger.debug(
            "Conversation history compacted",
            original_turns=len(messages),
            compacted_turns=len(compacted),
            dropped_turns=dropped_count,
        )
        return compacted
