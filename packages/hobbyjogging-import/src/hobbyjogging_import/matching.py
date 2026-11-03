"""Temporal matching of activities across sources.

Matching is based on overlapping time windows rather than exact start times.
A normal match needs at least two minutes of overlap covering 60% of the
shorter activity. A FIT file may also be a contained segment: when the
canonical activity is larger, at least 90% of the FIT window must fall inside
it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

MIN_OVERLAP_S = 120.0
MIN_SHORTER_RATIO = 0.60
MIN_FIT_CONTAINED_RATIO = 0.90
LARGER_WINDOW_S = 60.0


@dataclass(frozen=True)
class ActivityWindow:
    """A canonical activity's time span."""

    activity_id: str
    start: datetime
    end: datetime

    @property
    def duration_s(self) -> float:
        return (self.end - self.start).total_seconds()


@dataclass(frozen=True)
class MatchCandidate:
    """A possible canonical activity for an imported activity."""

    activity_id: str
    match_method: str
    confidence: float
    overlap_s: float
    shorter_ratio: float
    fit_contained_ratio: float | None = None


class AmbiguousMatchError(RuntimeError):
    """Raised when an activity has more than one plausible canonical match."""

    def __init__(self, matches: list[MatchCandidate]):
        self.matches = matches
        super().__init__(
            "ambiguous activity match: "
            + ", ".join(match.activity_id for match in matches)
        )


def match_window(
    candidate: ActivityWindow,
    existing: ActivityWindow,
    *,
    candidate_is_fit: bool = False,
) -> MatchCandidate | None:
    """Return a match when two activity windows overlap significantly."""
    overlap_s = _overlap_s(candidate, existing)
    candidate_duration = candidate.duration_s
    existing_duration = existing.duration_s

    if overlap_s <= 0 or candidate_duration <= 0 or existing_duration <= 0:
        return None

    shorter_ratio = overlap_s / min(candidate_duration, existing_duration)
    fit_contained_ratio = (
        overlap_s / candidate_duration if candidate_is_fit else None
    )

    if (
        candidate_is_fit
        and existing_duration > candidate_duration + LARGER_WINDOW_S
    ):
        if (
            fit_contained_ratio is None
            or fit_contained_ratio < MIN_FIT_CONTAINED_RATIO
            or overlap_s < MIN_OVERLAP_S
        ):
            return None

        return MatchCandidate(
            activity_id=existing.activity_id,
            match_method="contained_fit",
            confidence=round(fit_contained_ratio, 4),
            overlap_s=overlap_s,
            shorter_ratio=round(shorter_ratio, 4),
            fit_contained_ratio=round(fit_contained_ratio, 4),
        )

    if overlap_s < MIN_OVERLAP_S or shorter_ratio < MIN_SHORTER_RATIO:
        return None

    return MatchCandidate(
        activity_id=existing.activity_id,
        match_method="temporal_overlap",
        confidence=round(shorter_ratio, 4),
        overlap_s=overlap_s,
        shorter_ratio=round(shorter_ratio, 4),
        fit_contained_ratio=(
            round(fit_contained_ratio, 4)
            if fit_contained_ratio is not None
            else None
        ),
    )


def find_matches(
    candidate: ActivityWindow,
    existing: list[ActivityWindow],
    *,
    candidate_is_fit: bool = False,
) -> list[MatchCandidate]:
    """Return all plausible matches, best first."""
    matches = [
        match
        for window in existing
        if (
            match := match_window(
                candidate,
                window,
                candidate_is_fit=candidate_is_fit,
            )
        )
        is not None
    ]
    return sorted(
        matches,
        key=lambda match: (
            -match.confidence,
            -match.overlap_s,
            match.activity_id,
        ),
    )


def select_unique_match(
    matches: list[MatchCandidate],
) -> MatchCandidate | None:
    """Return the only match, or raise when several remain ambiguous."""
    if not matches:
        return None

    if len(matches) > 1:
        raise AmbiguousMatchError(matches)

    return matches[0]


def linked_activity(
    connection: sqlite3.Connection,
    source_record_id: int,
):
    """Return the canonical activity already linked to a source record."""
    return connection.execute(
        """
        SELECT activity_id, match_method, confidence
        FROM activity_sources
        WHERE source_record_id = ?
        ORDER BY is_primary DESC, id
        LIMIT 1
        """,
        (source_record_id,),
    ).fetchone()


class ActivityMatcher:
    """Find canonical activities overlapping an imported activity."""

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def find(
        self,
        *,
        started_at_utc: str,
        source: str,
        elapsed_s: float = 0,
        duration_s: float = 0,
        exclude_activity_id: str | None = None,
        search_days: int = 2,
    ) -> list[MatchCandidate]:
        start = parse_utc(started_at_utc)
        window_s = elapsed_s if elapsed_s > 0 else duration_s

        if start is None or window_s <= 0:
            return []

        candidate = ActivityWindow(
            activity_id="__candidate__",
            start=start,
            end=start + timedelta(seconds=window_s),
        )
        windows = self._windows(
            start.date(),
            search_days=search_days,
            exclude_activity_id=exclude_activity_id,
        )
        return find_matches(
            candidate,
            windows,
            candidate_is_fit=source == "fit",
        )

    def _windows(
        self,
        center: date,
        *,
        search_days: int,
        exclude_activity_id: str | None,
    ) -> list[ActivityWindow]:
        first_date = (center - timedelta(days=search_days)).isoformat()
        last_date = (center + timedelta(days=search_days)).isoformat()
        sql = """
            SELECT id, started_at_utc, elapsed_s, duration_s
            FROM activities
            WHERE local_date BETWEEN ? AND ?
              AND started_at_utc IS NOT NULL
              AND started_at_utc != ''
        """
        params: list[object] = [first_date, last_date]

        if exclude_activity_id is not None:
            sql += " AND id != ?"
            params.append(exclude_activity_id)

        rows = self.connection.execute(sql, params).fetchall()
        windows: list[ActivityWindow] = []

        for row in rows:
            start = parse_utc(row["started_at_utc"])
            window_s = row["elapsed_s"] if row["elapsed_s"] > 0 else row["duration_s"]

            if start is None or window_s <= 0:
                continue

            windows.append(
                ActivityWindow(
                    activity_id=row["id"],
                    start=start,
                    end=start + timedelta(seconds=window_s),
                )
            )

        return windows


def parse_utc(value: object) -> datetime | None:
    """Parse an ISO timestamp as an aware UTC datetime."""
    if not value:
        return None

    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    return moment.astimezone(timezone.utc)


def _overlap_s(first: ActivityWindow, second: ActivityWindow) -> float:
    return max(
        0.0,
        (
            min(first.end, second.end) - max(first.start, second.start)
        ).total_seconds(),
    )
