"""Durable storage and domain models for developer review decisions.

Provides SQLite-backed persistence, thread safety, validation, and chronological
audit history for requirement-to-code candidate link decisions.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_DECISION_STATUSES: frozenset[str] = frozenset(
    {"accepted", "rejected", "needs_review"}
)


@dataclass(frozen=True)
class ReviewDecision:
    """Current recorded developer review decision for a trace link candidate."""

    project_id: str
    requirement_id: str
    target_id: str
    decision: str
    rationale: str
    created_at: str
    updated_at: str
    revision_count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert decision to a JSON-serializable dictionary."""
        return {
            "project_id": self.project_id,
            "requirement_id": self.requirement_id,
            "target_id": self.target_id,
            "decision": self.decision,
            "rationale": self.rationale,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "revision_count": self.revision_count,
        }


@dataclass(frozen=True)
class ReviewDecisionEvent:
    """Historical audit event recording a single decision creation or revision."""

    id: int
    project_id: str
    requirement_id: str
    target_id: str
    decision: str
    rationale: str
    created_at: str
    revision_number: int

    def to_dict(self) -> dict[str, Any]:
        """Convert audit event to a JSON-serializable dictionary."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "requirement_id": self.requirement_id,
            "target_id": self.target_id,
            "decision": self.decision,
            "rationale": self.rationale,
            "created_at": self.created_at,
            "revision_number": self.revision_number,
        }


class ReviewStore:
    """Thread-safe SQLite store for candidate review decisions and audit logs."""

    DEFAULT_DB_PATH = Path("data/reviews/reviews.db")

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Initialize the review store with a file path or ':memory:' database."""
        if db_path is None:
            self.db_path = self.DEFAULT_DB_PATH
        elif str(db_path) == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = Path(db_path)

        if isinstance(self.db_path, Path):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        with self._lock:
            if str(self.db_path) != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA foreign_keys=ON;")
            self._init_schema()

    def _init_schema(self) -> None:
        """Create necessary database tables and indexes if they do not exist."""
        cursor = self._conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS review_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                requirement_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                decision TEXT NOT NULL CHECK(
                    decision IN ('accepted', 'rejected', 'needs_review')
                ),
                rationale TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revision_count INTEGER NOT NULL DEFAULT 1,
                UNIQUE(project_id, requirement_id, target_id)
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_review_decisions_req
                ON review_decisions (project_id, requirement_id);
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_review_decisions_target
                ON review_decisions (project_id, requirement_id, target_id);
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS review_decision_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                requirement_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                decision TEXT NOT NULL CHECK(
                    decision IN ('accepted', 'rejected', 'needs_review')
                ),
                rationale TEXT NOT NULL,
                created_at TEXT NOT NULL,
                revision_number INTEGER NOT NULL
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_review_history_target
                ON review_decision_history (project_id, requirement_id, target_id);
            """
        )
        self._conn.commit()

    @staticmethod
    def validate_inputs(
        project_id: str,
        requirement_id: str,
        target_id: str,
        decision: str,
        rationale: str | None = None,
    ) -> tuple[str, str, str, str, str]:
        """Validate review inputs, returning normalized params or raising ValueError."""
        if not project_id or not project_id.strip():
            raise ValueError("project_id is required and cannot be empty.")
        if not requirement_id or not requirement_id.strip():
            raise ValueError("requirement_id is required and cannot be empty.")
        if not target_id or not target_id.strip():
            raise ValueError("target_id is required and cannot be empty.")

        clean_dec = (decision or "").strip().lower()
        if clean_dec not in VALID_DECISION_STATUSES:
            sorted_valid = ", ".join(sorted(VALID_DECISION_STATUSES))
            raise ValueError(
                f"Invalid decision status '{decision}'. Must be one of: {sorted_valid}"
            )

        clean_rat = (rationale or "").strip()
        if clean_dec in ("accepted", "rejected") and not clean_rat:
            raise ValueError(
                f"A non-empty rationale is required for '{clean_dec}' decisions."
            )

        return (
            project_id.strip(),
            requirement_id.strip(),
            target_id.strip(),
            clean_dec,
            clean_rat,
        )

    def record_decision(
        self,
        project_id: str,
        requirement_id: str,
        target_id: str,
        decision: str,
        rationale: str = "",
    ) -> ReviewDecision:
        """Record or revise a review decision with audit history retention."""
        (
            norm_project,
            norm_req,
            norm_target,
            norm_decision,
            norm_rationale,
        ) = self.validate_inputs(
            project_id, requirement_id, target_id, decision, rationale
        )

        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT id, created_at, revision_count
                FROM review_decisions
                WHERE project_id = ? AND requirement_id = ? AND target_id = ?
                """,
                (norm_project, norm_req, norm_target),
            )
            row = cursor.fetchone()

            if row is None:
                rev_count = 1
                created_at = now
                updated_at = now
                cursor.execute(
                    """
                    INSERT INTO review_decisions (
                        project_id, requirement_id, target_id, decision,
                        rationale, created_at, updated_at, revision_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        norm_project,
                        norm_req,
                        norm_target,
                        norm_decision,
                        norm_rationale,
                        created_at,
                        updated_at,
                        rev_count,
                    ),
                )
            else:
                rev_count = int(row["revision_count"]) + 1
                created_at = str(row["created_at"])
                updated_at = now
                cursor.execute(
                    """
                    UPDATE review_decisions
                    SET decision = ?, rationale = ?, updated_at = ?, revision_count = ?
                    WHERE project_id = ? AND requirement_id = ? AND target_id = ?
                    """,
                    (
                        norm_decision,
                        norm_rationale,
                        updated_at,
                        rev_count,
                        norm_project,
                        norm_req,
                        norm_target,
                    ),
                )

            cursor.execute(
                """
                INSERT INTO review_decision_history (
                    project_id, requirement_id, target_id, decision,
                    rationale, created_at, revision_number
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    norm_project,
                    norm_req,
                    norm_target,
                    norm_decision,
                    norm_rationale,
                    now,
                    rev_count,
                ),
            )
            self._conn.commit()

            return ReviewDecision(
                project_id=norm_project,
                requirement_id=norm_req,
                target_id=norm_target,
                decision=norm_decision,
                rationale=norm_rationale,
                created_at=created_at,
                updated_at=updated_at,
                revision_count=rev_count,
            )

    def get_decision(
        self,
        project_id: str,
        requirement_id: str,
        target_id: str,
    ) -> ReviewDecision | None:
        """Fetch current decision for a candidate link, or None if unreviewed."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT project_id, requirement_id, target_id, decision,
                       rationale, created_at, updated_at, revision_count
                FROM review_decisions
                WHERE project_id = ? AND requirement_id = ? AND target_id = ?
                """,
                (project_id.strip(), requirement_id.strip(), target_id.strip()),
            )
            row = cursor.fetchone()
            if row is None:
                return None

            return ReviewDecision(
                project_id=row["project_id"],
                requirement_id=row["requirement_id"],
                target_id=row["target_id"],
                decision=row["decision"],
                rationale=row["rationale"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                revision_count=int(row["revision_count"]),
            )

    def get_decisions_for_requirement(
        self,
        project_id: str,
        requirement_id: str,
    ) -> list[ReviewDecision]:
        """Fetch all recorded decisions for a requirement."""
        with self._lock:
            cursor = self._conn.cursor()
            cursor.execute(
                """
                SELECT project_id, requirement_id, target_id, decision,
                       rationale, created_at, updated_at, revision_count
                FROM review_decisions
                WHERE project_id = ? AND requirement_id = ?
                ORDER BY updated_at DESC, id DESC
                """,
                (project_id.strip(), requirement_id.strip()),
            )
            rows = cursor.fetchall()
            return [
                ReviewDecision(
                    project_id=row["project_id"],
                    requirement_id=row["requirement_id"],
                    target_id=row["target_id"],
                    decision=row["decision"],
                    rationale=row["rationale"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    revision_count=int(row["revision_count"]),
                )
                for row in rows
            ]

    def get_history(
        self,
        project_id: str,
        requirement_id: str,
        target_id: str | None = None,
    ) -> list[ReviewDecisionEvent]:
        """Fetch chronological audit history for a candidate link or requirement."""
        with self._lock:
            cursor = self._conn.cursor()
            if target_id is not None:
                cursor.execute(
                    """
                    SELECT id, project_id, requirement_id, target_id, decision,
                           rationale, created_at, revision_number
                    FROM review_decision_history
                    WHERE project_id = ? AND requirement_id = ? AND target_id = ?
                    ORDER BY id ASC
                    """,
                    (project_id.strip(), requirement_id.strip(), target_id.strip()),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, project_id, requirement_id, target_id, decision,
                           rationale, created_at, revision_number
                    FROM review_decision_history
                    WHERE project_id = ? AND requirement_id = ?
                    ORDER BY id ASC
                    """,
                    (project_id.strip(), requirement_id.strip()),
                )
            rows = cursor.fetchall()
            return [
                ReviewDecisionEvent(
                    id=int(row["id"]),
                    project_id=row["project_id"],
                    requirement_id=row["requirement_id"],
                    target_id=row["target_id"],
                    decision=row["decision"],
                    rationale=row["rationale"],
                    created_at=row["created_at"],
                    revision_number=int(row["revision_number"]),
                )
                for row in rows
            ]

    def close(self) -> None:
        """Close SQLite database connection."""
        with self._lock:
            self._conn.close()


__all__ = [
    "ReviewDecision",
    "ReviewDecisionEvent",
    "ReviewStore",
    "VALID_DECISION_STATUSES",
]
