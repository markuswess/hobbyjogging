"""What a task receives while it runs."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from hobbyjogging_core import TrainingRepository, TrainingWriter


@dataclass(frozen=True)
class Scope:
    """Optional restriction of a task to part of the database."""

    start: date | None = None
    end: date | None = None
    entity_id: str | None = None
    limit: int | None = None


@dataclass
class TaskContext:
    """State shared between the runner and one task.

    Tasks write through :attr:`writer` (never raw SQL over canonical values) so
    manual values and ownership rules keep holding. Tasks must not commit; the
    runner wraps the whole run in one transaction and rolls it back for a dry
    run.
    """

    connection: sqlite3.Connection
    scope: Scope = field(default_factory=Scope)
    dry_run: bool = False
    output: Path | None = None
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    output_lines: list[str] = field(default_factory=list)
    details: dict[str, object] = field(default_factory=dict)
    _repository: TrainingRepository | None = field(default=None, repr=False)
    _writer: TrainingWriter | None = field(default=None, repr=False)

    @property
    def repository(self) -> TrainingRepository:
        """Lazy repository over the canonical model."""
        if self._repository is None:
            self._repository = TrainingRepository(self.connection)
        return self._repository

    @property
    def writer(self) -> TrainingWriter:
        """Lazy writer; the only supported way to change stored values."""
        if self._writer is None:
            self._writer = TrainingWriter(self.connection)
        return self._writer

    def count(self, name: str, amount: int = 1) -> None:
        """Add to one named counter shown in the run summary."""
        self.counts[name] = self.counts.get(name, 0) + amount

    def note(self, line: str) -> None:
        """Add a short line to the run summary."""
        self.notes.append(line)

    def order_counts(self, names: tuple[str, ...]) -> None:
        """Reorder the summary counters, filling declared ones with zero."""
        ordered = {name: self.counts.get(name, 0) for name in names}
        ordered.update(
            (name, value)
            for name, value in self.counts.items()
            if name not in ordered
        )
        self.counts = ordered

    def write_output(self) -> Path | None:
        """Write :attr:`output_lines` when an output path was given.

        This is an external side effect, so it also happens during a dry run:
        the review list is exactly what a dry run is for.
        """
        if self.output is None:
            return None
        self.output.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(self.output_lines).rstrip("\n")
        self.output.write_text(f"{text}\n" if text else "")
        return self.output
