"""SQLite persistent session and timeline state storage."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SQLiteSessionStore:
    """Thread-safe persistent session store backed by SQLite."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.getenv("SQLITE_DB_PATH", "editor_state.db")
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initializes tables for sessions, timeline snapshots, VFX presets, and conversation events."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        metadata_json TEXT
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS timeline_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        turn_index INTEGER,
                        snapshot_json TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS vfx_presets (
                        preset_id TEXT PRIMARY KEY,
                        preset_name TEXT,
                        category TEXT,
                        config_json TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_events (
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        role TEXT,
                        content TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # Populate default VFX presets if empty
                cur = conn.execute("SELECT COUNT(*) as cnt FROM vfx_presets")
                if cur.fetchone()["cnt"] == 0:
                    conn.executemany(
                        "INSERT INTO vfx_presets (preset_id, preset_name, category, config_json) VALUES (?, ?, ?, ?)",
                        [
                            ("preset_pip_topright", "Top-Right PiP Facecam", "pip", json.dumps({"position": "top-right", "scale": 0.28, "mask": "rounded_rect", "border": 4})),
                            ("preset_pip_circle", "Circular Reaction PiP", "pip", json.dumps({"position": "bottom-right", "scale": 0.25, "mask": "circle", "border": 3})),
                            ("preset_rotoscope_actor", "Actor Silhouette Rotoscope", "mask", json.dumps({"shape": "silhouette", "feather": 2.5, "invert": False})),
                        ],
                    )
                conn.commit()

    def save_session_state(self, session_id: str, state_dict: dict[str, Any], turn_index: int = 0) -> None:
        """Persists the full timeline snapshot and session metadata to SQLite."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO sessions (session_id, updated_at, metadata_json)
                    VALUES (?, CURRENT_TIMESTAMP, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        updated_at = CURRENT_TIMESTAMP,
                        metadata_json = excluded.metadata_json
                    """,
                    (session_id, json.dumps({"last_turn": turn_index})),
                )
                conn.execute(
                    "INSERT INTO timeline_snapshots (session_id, turn_index, snapshot_json) VALUES (?, ?, ?)",
                    (session_id, turn_index, json.dumps(state_dict)),
                )
                conn.commit()
                logger.debug("Session snapshot stored in SQLite", session_id=session_id, turn_index=turn_index)

    def load_latest_session_state(self, session_id: str) -> dict[str, Any] | None:
        """Loads the most recent timeline snapshot for a session."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute(
                    "SELECT snapshot_json FROM timeline_snapshots WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                    (session_id,),
                )
                row = cur.fetchone()
                if row:
                    return json.loads(row["snapshot_json"])
                return None

    def record_conversation_event(self, session_id: str, role: str, content: str) -> None:
        """Records a user/agent turn into persistent conversation events."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO conversation_events (session_id, role, content) VALUES (?, ?, ?)",
                    (session_id, role, content),
                )
                conn.commit()

    def get_vfx_preset(self, preset_id: str) -> dict[str, Any] | None:
        """Retrieves a persistent VFX preset by identifier."""
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.execute("SELECT config_json FROM vfx_presets WHERE preset_id = ?", (preset_id,))
                row = cur.fetchone()
                if row:
                    return json.loads(row["config_json"])
                return None


# Global session store instance
session_store = SQLiteSessionStore()
