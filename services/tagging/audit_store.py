"""Purpose: Persist metadata snapshots, review state, and tagging history in SQLite."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from services.tagging.schema import CanonicalTrack, DiffReport, utc_now_iso

APP_NAME = "WalkmanPlaylistCreator"
DB_FILENAME = "tagging_audit.sqlite3"


class TaggingAuditStore:
    """SQLite-backed persistence for safe tagging operations."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = self._resolve_db_path(db_path)
        self._initialize()

    def record_snapshot(
        self,
        *,
        file_path: str,
        before: CanonicalTrack,
        after: CanonicalTrack,
        diff_report: DiffReport,
        status: str,
        source: str,
    ) -> int:
        """Store a before/after snapshot for a proposed or completed write."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO metadata_snapshots (
                    file_path,
                    created_at,
                    status,
                    source,
                    before_json,
                    after_json,
                    diff_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_path,
                    utc_now_iso(),
                    status,
                    source,
                    json.dumps(before.to_dict()),
                    json.dumps(after.to_dict()),
                    json.dumps(diff_report.to_dict()),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def enqueue_review(
        self,
        *,
        file_path: str,
        diff_report: DiffReport,
        proposed_track: CanonicalTrack,
        reason: str,
    ) -> int:
        """Add a track to the review queue."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO review_queue (
                    file_path,
                    created_at,
                    status,
                    reason,
                    diff_json,
                    proposed_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    file_path,
                    utc_now_iso(),
                    "pending",
                    reason,
                    json.dumps(diff_report.to_dict()),
                    json.dumps(proposed_track.to_dict()),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def list_review_items(self, status: str = "pending") -> list[dict[str, object]]:
        """Return queued review items in creation order."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, file_path, created_at, status, reason, diff_json, proposed_json
                FROM review_queue
                WHERE status = ?
                ORDER BY created_at ASC
                """,
                (status,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_review_status(self, review_id: int, status: str) -> None:
        """Update the workflow state of a queued review item."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE review_queue
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, utc_now_iso(), review_id),
            )
            conn.commit()

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL,
                    before_json TEXT NOT NULL,
                    after_json TEXT NOT NULL,
                    diff_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS review_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    diff_json TEXT NOT NULL,
                    proposed_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def _resolve_db_path(self, db_path: Path | None) -> Path:
        candidate = db_path or get_default_db_path()
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate
        except PermissionError:
            fallback = Path.cwd() / ".app_state" / DB_FILENAME
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback


def get_default_db_path() -> Path:
    """Return the persistent SQLite location for tagging state."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / APP_NAME / DB_FILENAME
    return home / ".local" / "state" / APP_NAME / DB_FILENAME
