"""Schema evolution and data maintenance for the training database."""

from . import backfills, recompute  # noqa: F401 - importing registers the tasks
from .context import Scope, TaskContext
from .registry import Task, all_tasks, get_task, task
from .runner import TaskRun, run_task

__all__ = [
    "Scope",
    "Task",
    "TaskContext",
    "TaskRun",
    "all_tasks",
    "get_task",
    "run_task",
    "task",
]
