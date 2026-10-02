"""Unit tests for SQLite persistent session store, vector index, and history compaction."""

import os
import tempfile

import pytest

from app.memory.async_memory import consolidate_session_memory_async
from app.memory.compaction import HistoryCompactor
from app.memory.session_store import SQLiteSessionStore
from app.memory.vector_store import LocalVectorStore


def test_sqlite_session_persistence():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "test_editor.db")
        store = SQLiteSessionStore(db_path=db_path)

        state = {"tracks": [{"track_id": "V1", "clips": 1}], "playhead": 240}
        store.save_session_state("session_123", state, turn_index=1)

        loaded = store.load_latest_session_state("session_123")
        assert loaded is not None
        assert loaded["playhead"] == 240
        assert loaded["tracks"][0]["track_id"] == "V1"


def test_vector_store_semantic_search():
    store = LocalVectorStore()
    results = store.search("Picture in Picture facecam placement")
    assert len(results) > 0
    top_doc = results[0]
    assert "PiP" in top_doc["title"] or "Picture in Picture" in top_doc["title"]


def test_history_compactor_keyframes():
    raw_keyframes = [
        {"frame": 0, "x": 0.35, "y": 0.50, "scale": 1.0},
        {"frame": 100, "x": 0.50, "y": 0.52, "scale": 1.05},
        {"frame": 200, "x": 0.65, "y": 0.55, "scale": 1.10},
    ]
    summary = HistoryCompactor.compact_keyframe_array(raw_keyframes)
    assert summary["is_compacted"] is True
    assert summary["frame_count"] == 3
    assert summary["x_bounds"] == [0.35, 0.65]


def test_history_compactor_sliding_window():
    compactor = HistoryCompactor(max_history_turns=4)
    messages = [
        {"role": "user", "content": "Initial prompt"},
        {"role": "assistant", "content": "Initial reply"},
        {"role": "user", "content": "Turn 2"},
        {"role": "assistant", "content": "Turn 2 reply"},
        {"role": "user", "content": "Turn 3"},
        {"role": "assistant", "content": "Turn 3 reply"},
    ]
    compacted = compactor.compact_conversation_history(messages)
    assert len(compacted) <= 5
    assert any("[Context Compaction:" in m.get("content", "") for m in compacted)


@pytest.mark.asyncio
async def test_async_memory_consolidation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "async_test.db")
        store = SQLiteSessionStore(db_path=db_path)
        # Patch global session store
        import app.memory.async_memory as async_mem_mod
        original_store = async_mem_mod.session_store
        async_mem_mod.session_store = store

        try:
            await consolidate_session_memory_async(
                session_id="test_async_sess",
                timeline_state={"state": "active"},
                user_utterance="I always prefer 1080p ProRes export",
                turn_index=1,
            )
            loaded = store.load_latest_session_state("test_async_sess")
            assert loaded["state"] == "active"
        finally:
            async_mem_mod.session_store = original_store
