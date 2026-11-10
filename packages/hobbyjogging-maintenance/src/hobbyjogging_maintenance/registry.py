"""Registry of maintenance tasks.

A task is a named, dry-runnable unit of data work. Two kinds exist:

- ``backfill`` — a one-time transformation applied after a schema or logic
  change. It is recorded in ``data_migrations`` and skipped once applied; a
  changed transformation needs a new id (``..._v2``), never an edit.
- ``recompute`` — an idempotent re-derivation of stored values from their
  authoritative inputs. It runs every time and is only logged.

Schema changes themselves do not live here; they are ordered SQL migrations in
``hobbyjogging_core.db.migrations``.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .context import TaskContext

TaskKind = Literal["backfill", "recompute"]
TaskFunction = Callable[["TaskContext"], None]

KINDS: tuple[TaskKind, ...] = ("backfill", "recompute")


@dataclass(frozen=True)
class Task:
    """One registered unit of data work."""

    id: str
    kind: TaskKind
    description: str
    run: TaskFunction

    @property
    def applied_once(self) -> bool:
        """Whether the task is skipped after it has been applied."""
        return self.kind == "backfill"


_REGISTRY: dict[str, Task] = {}


def task(
    task_id: str,
    *,
    kind: TaskKind = "backfill",
    description: str = "",
) -> Callable[[TaskFunction], TaskFunction]:
    """Register a task function under ``task_id``."""
    if kind not in KINDS:
        raise ValueError(f"unknown task kind: {kind!r}")
    if not task_id:
        raise ValueError("a task needs a non-empty id")

    def register(function: TaskFunction) -> TaskFunction:
        if task_id in _REGISTRY:
            raise ValueError(f"duplicate task id: {task_id}")
        _REGISTRY[task_id] = Task(
            id=task_id,
            kind=kind,
            description=" ".join(description.split()),
            run=function,
        )
        return function

    return register


def all_tasks() -> list[Task]:
    """Return every registered task in registration order."""
    return list(_REGISTRY.values())


def get_task(task_id: str) -> Task:
    """Return one registered task by id."""
    try:
        return _REGISTRY[task_id]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "none"
        raise KeyError(
            f"unknown task {task_id!r} (known tasks: {known})"
        ) from None


@contextlib.contextmanager
def preserve_registry() -> Iterator[None]:
    """Restore the global registry afterwards (used by tests)."""
    saved = dict(_REGISTRY)
    try:
        yield
    finally:
        _REGISTRY.clear()
        _REGISTRY.update(saved)
