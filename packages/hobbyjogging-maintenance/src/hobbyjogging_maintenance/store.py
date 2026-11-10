"""Bookkeeping for applied backfills and maintenance runs."""

from __future__ import annotations

import json
import sqlite3

from .registry import Task


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def applied_ids(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    """Return ``{task_id: row}`` for every applied backfill."""
    rows = connection.execute(
        """
        SELECT id, applied_at, details_json
        FROM data_migrations
        ORDER BY applied_at, id
        """
    ).fetchall()
    return {row["id"]: row for row in rows}


def is_applied(connection: sqlite3.Connection, task_id: str) -> bool:
    """Whether ``task_id`` is recorded as applied."""
    row = connection.execute(
        "SELECT 1 FROM data_migrations WHERE id = ?",
        (task_id,),
    ).fetchone()
    return row is not None


def record_applied(
    connection: sqlite3.Connection,
    task_id: str,
    details: dict[str, object],
) -> None:
    """Record a backfill as applied. Does not commit; the runner does."""
    connection.execute(
        """
        INSERT INTO data_migrations (id, details_json)
        VALUES (?, ?)
        ON CONFLICT (id) DO UPDATE SET
            applied_at = CURRENT_TIMESTAMP,
            details_json = excluded.details_json
        """,
        (task_id, _dump(details)),
    )


def start_run(
    connection: sqlite3.Connection,
    task: Task,
    *,
    dry_run: bool,
) -> int:
    """Insert a running row and commit, so it survives a failed task."""
    cursor = connection.execute(
        """
        INSERT INTO maintenance_runs (task, kind, dry_run, status)
        VALUES (?, ?, ?, 'running')
        """,
        (task.id, task.kind, 1 if dry_run else 0),
    )
    connection.commit()
    return cursor.lastrowid


def finish_run(
    connection: sqlite3.Connection,
    run_id: int,
    status: str,
    *,
    counts: dict[str, int] | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Close a run row and commit."""
    payload = {"counts": counts or {}}
    if details:
        payload["details"] = details
    connection.execute(
        """
        UPDATE maintenance_runs
        SET finished_at = CURRENT_TIMESTAMP, status = ?, details_json = ?
        WHERE id = ?
        """,
        (status, _dump(payload), run_id),
    )
    connection.commit()


def recent_runs(
    connection: sqlite3.Connection,
    limit: int = 10,
) -> list[sqlite3.Row]:
    """Return the most recent runs, newest first."""
    return connection.execute(
        """
        SELECT id, task, kind, started_at, finished_at, dry_run, status,
               details_json
        FROM maintenance_runs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
