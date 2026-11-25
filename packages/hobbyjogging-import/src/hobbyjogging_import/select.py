"""Resolve a human selector to an activity, period or equipment id.

The commands accept an exact id, an ISO date, ``last``, or a name substring.
An ambiguous date or name lists the candidates and refuses to guess; an
interactive caller may pass a ``choose`` callback to pick from the list.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Callable

Chooser = Callable[[list["Candidate"]], str | None]


@dataclass(frozen=True)
class Candidate:
    id: str
    date: str
    label: str
    detail: str = ""

    def line(self) -> str:
        parts = [self.id, self.date, self.label]
        if self.detail:
            parts.append(self.detail)
        return "  ".join(part for part in parts if part)


class SelectionError(ValueError):
    """No entity, or more than one, for a selector."""

    def __init__(self, message: str, candidates: list[Candidate] | None = None):
        self.candidates = candidates or []
        if self.candidates:
            listing = "\n".join(
                f"  {candidate.line()}" for candidate in self.candidates
            )
            message = f"{message}\n{listing}\nuse the id"
        super().__init__(message)


def resolve_activity(
    connection: sqlite3.Connection,
    selector: str,
    *,
    choose: Chooser | None = None,
    include_excluded: bool = False,
) -> str:
    """Resolve an activity id, date, ``last`` or name substring."""
    token = str(selector or "").strip()
    if not token:
        raise SelectionError("activity selector is empty")

    visible = "" if include_excluded else " AND excluded_at IS NULL"
    row = connection.execute(
        f"SELECT id FROM activities WHERE id = ?{visible}",
        (token,),
    ).fetchone()
    if row is not None:
        return row["id"]

    if token.lower() == "last":
        row = connection.execute(
            f"""
            SELECT id FROM activities
            WHERE excluded_at IS NULL
            ORDER BY local_date DESC, COALESCE(started_at_utc, ''), id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            raise SelectionError("no activities stored")
        return row["id"]

    try:
        day = date.fromisoformat(token)
    except ValueError:
        day = None

    if day is not None:
        rows = connection.execute(
            f"""
            SELECT id, local_date, sport, name FROM activities
            WHERE local_date = ?{visible}
            ORDER BY COALESCE(started_at_utc, ''), id
            """,
            (day.isoformat(),),
        ).fetchall()
        return _one(
            rows,
            "no activity on " + day.isoformat(),
            f"ambiguous date {day.isoformat()}",
            choose,
            _activity_candidate,
        )

    rows = connection.execute(
        f"""
        SELECT id, local_date, sport, name FROM activities
        WHERE instr(lower(name), lower(?)) > 0{visible}
        ORDER BY local_date, COALESCE(started_at_utc, ''), id
        """,
        (token,),
    ).fetchall()
    return _one(
        rows,
        f"no activity matching {token!r}",
        f"ambiguous activity name {token!r}",
        choose,
        _activity_candidate,
    )


def resolve_equipment(
    connection: sqlite3.Connection,
    selector: str,
    *,
    choose: Chooser | None = None,
) -> str:
    """Resolve an equipment id or name substring."""
    token = str(selector or "").strip()
    if not token:
        raise SelectionError("equipment selector is empty")

    row = connection.execute(
        "SELECT id FROM equipment WHERE id = ?",
        (token,),
    ).fetchone()
    if row is not None:
        return row["id"]

    rows = connection.execute(
        """
        SELECT id, name, type, acquired_on, retired_on FROM equipment
        WHERE instr(lower(name), lower(?)) > 0
           OR instr(lower(brand || ' ' || model), lower(?)) > 0
        ORDER BY name, id
        """,
        (token, token),
    ).fetchall()
    return _one(
        rows,
        f"no equipment matching {token!r}",
        f"ambiguous equipment {token!r}",
        choose,
        lambda row: Candidate(
            id=row["id"],
            date=str(row["acquired_on"] or ""),
            label=row["name"],
            detail=row["type"],
        ),
    )


def resolve_period(
    connection: sqlite3.Connection,
    selector: str,
    *,
    choose: Chooser | None = None,
) -> str:
    """Resolve a period id, ISO date inside it, or label substring."""
    token = str(selector or "").strip()
    if not token:
        raise SelectionError("period selector is empty")

    row = connection.execute(
        "SELECT id FROM training_periods "
        "WHERE id = ? AND excluded_at IS NULL",
        (token,),
    ).fetchone()
    if row is not None:
        return row["id"]

    try:
        day = date.fromisoformat(token).isoformat()
    except ValueError:
        day = None

    if day is not None:
        rows = connection.execute(
            """
            SELECT id, kind, label, start_date, end_date
            FROM training_periods
            WHERE excluded_at IS NULL
              AND start_date <= ?
              AND COALESCE(end_date, start_date) >= ?
            ORDER BY start_date, id
            """,
            (day, day),
        ).fetchall()
        return _one(
            rows,
            f"no period on {day}",
            f"ambiguous period date {day}",
            choose,
            _period_candidate,
        )

    rows = connection.execute(
        """
        SELECT id, kind, label, start_date, end_date
        FROM training_periods
        WHERE excluded_at IS NULL AND instr(lower(label), lower(?)) > 0
        ORDER BY start_date, id
        """,
        (token,),
    ).fetchall()
    return _one(
        rows,
        f"no period matching {token!r}",
        f"ambiguous period label {token!r}",
        choose,
        _period_candidate,
    )


def prompt_candidate(
    candidates: list[Candidate],
    *,
    read: Callable[[str], str] = input,
    print: Callable[..., None] = print,
) -> str | None:
    """Print candidates and read a 1-based choice; blank cancels."""
    print("Matched several records:")
    for index, candidate in enumerate(candidates, start=1):
        print(f"  {index}) {candidate.line()}")
    try:
        answer = read(f"pick (1-{len(candidates)}, blank=cancel): ").strip()
    except EOFError:
        return None
    if not answer:
        return None
    try:
        index = int(answer)
    except ValueError:
        return None
    if not 1 <= index <= len(candidates):
        return None
    return candidates[index - 1].id


def _one(
    rows,
    missing: str,
    ambiguous: str,
    choose: Chooser | None,
    builder,
) -> str:
    candidates = [builder(row) for row in rows]
    if not candidates:
        raise SelectionError(missing)
    if len(candidates) == 1:
        return candidates[0].id
    if choose is not None:
        selected = choose(candidates)
        if selected in {candidate.id for candidate in candidates}:
            return selected
        raise SelectionError(ambiguous, candidates)
    raise SelectionError(ambiguous, candidates)


def _activity_candidate(row) -> Candidate:
    return Candidate(
        id=row["id"],
        date=row["local_date"],
        label=row["name"] or row["sport"],
        detail=row["sport"],
    )


def _period_candidate(row) -> Candidate:
    end = row["end_date"] or row["start_date"]
    return Candidate(
        id=row["id"],
        date=f"{row['start_date']}..{end}",
        label=row["label"] or row["kind"],
        detail=row["kind"],
    )
