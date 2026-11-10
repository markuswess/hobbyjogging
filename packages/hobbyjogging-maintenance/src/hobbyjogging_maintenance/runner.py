"""Run maintenance tasks with scoping, dry-run, and bookkeeping."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .context import Scope, TaskContext
from .registry import Task
from .store import finish_run, is_applied, record_applied, start_run


@dataclass
class TaskRun:
    """The outcome of one task run."""

    task: Task
    status: str = "ok"  # ok | skipped | failed
    dry_run: bool = False
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)
    error: str | None = None
    output: Path | None = None

    @property
    def ok(self) -> bool:
        return self.status != "failed"


class _Rollback(Exception):
    """Internal signal: a dry run ends by rolling its transaction back."""


def run_task(
    connection: sqlite3.Connection,
    task: Task,
    *,
    scope: Scope | None = None,
    dry_run: bool = False,
    force: bool = False,
    output: Path | None = None,
) -> TaskRun:
    """Run one task inside a transaction.

    A dry run executes the real code path and then rolls the transaction back,
    so it cannot drift from a real run. Applied backfills are skipped unless
    ``force`` is set. Every run, dry or not, is recorded in
    ``maintenance_runs``.
    """
    if task.applied_once and not force and is_applied(connection, task.id):
        return TaskRun(task=task, status="skipped", dry_run=dry_run)

    context = TaskContext(
        connection=connection,
        scope=scope or Scope(),
        dry_run=dry_run,
        output=output,
    )
    run_id = start_run(connection, task, dry_run=dry_run)

    try:
        with connection:
            task.run(context)
            if task.applied_once and not dry_run:
                record_applied(connection, task.id, context.details)
            if dry_run:
                raise _Rollback
    except _Rollback:
        pass
    except Exception as exc:  # noqa: BLE001 - reported, then re-raised by the CLI
        finish_run(
            connection,
            run_id,
            "failed",
            counts=context.counts,
            details={**context.details, "error": str(exc)},
        )
        return TaskRun(
            task=task,
            status="failed",
            dry_run=dry_run,
            counts=context.counts,
            notes=context.notes,
            details=context.details,
            error=str(exc),
            output=output,
        )

    finish_run(
        connection,
        run_id,
        "ok",
        counts=context.counts,
        details=context.details,
    )
    return TaskRun(
        task=task,
        status="ok",
        dry_run=dry_run,
        counts=context.counts,
        notes=context.notes,
        details=context.details,
        output=output,
    )
