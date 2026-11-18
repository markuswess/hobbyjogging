"""Temporal matching of activities across sources.

Matching is based on overlapping time windows rather than exact start times.
A normal match needs at least two minutes of overlap covering 60% of the
shorter activity. Below two minutes the floor scales with that activity, so a
short session can still match. A FIT file may also be a contained segment:
when the canonical activity is larger, at least 90% of the FIT window must
fall inside it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from hobbyjogging_core.import_rules import source_profile
from hobbyjogging_core.sports import NO_DISTANCE_SPORTS

MIN_OVERLAP_S = 120.0
MIN_SHORTER_RATIO = 0.60
MIN_FIT_CONTAINED_RATIO = 0.90
LARGER_WINDOW_S = 60.0


def _required_overlap_s(shorter_duration: float) -> float:
    """Minimum overlap, capped so a short activity can still match.

    A flat 120 s floor excludes every activity shorter than two minutes
    outright: it can never overlap by more than its own length. Below
    200 s the required overlap scales with the shorter window, and
    ``MIN_SHORTER_RATIO`` carries the decision instead.
    """
    return min(MIN_OVERLAP_S, shorter_duration * MIN_SHORTER_RATIO)


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


@dataclass(frozen=True)
class MatchPolicy:
    """How loosely one source accepts a same-session match.

    The temporal window is shared; the distance and exact-twin tolerances are
    policy because cloud sources differ in how they round a track. The
    defaults are the Runalyze values that survived the 19-row review.
    """

    distance_ratio: float = 0.05
    distance_m: float = 100.0
    exact_duration_s: float = 2.0
    exact_distance_m: float = 10.0
    exact_twin: bool = True


@dataclass(frozen=True)
class MatchDecision:
    """The outcome of resolving one imported row against the canonical DB.

    ``activity_id`` is set only for a link. ``reason`` is stable enough to
    store in a review item: ``matched``, ``exact_twin``, ``ambiguous_match``,
    ``distance_mismatch``, ``no_temporal_match``, ``no_start``, ``no_duration``
    or ``create``.
    """

    activity_id: str | None
    reason: str
    match_method: str = ""
    confidence: float | None = None
    candidates: tuple[MatchCandidate, ...] = ()

    @property
    def linked(self) -> bool:
        return self.activity_id is not None

    @property
    def needs_review(self) -> bool:
        return self.activity_id is None and self.reason == "ambiguous_match"


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
    shorter_duration = min(candidate_duration, existing_duration)
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
            or overlap_s < _required_overlap_s(shorter_duration)
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

    if (
        overlap_s < _required_overlap_s(shorter_duration)
        or shorter_ratio < MIN_SHORTER_RATIO
    ):
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
            candidate_is_fit=_match_mode(source) == "contained_fit",
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
              AND excluded_at IS NULL
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


def decide_match(
    connection: sqlite3.Connection,
    *,
    source: str,
    started_at_utc: str | None,
    elapsed_s: float = 0,
    duration_s: float = 0,
    distance_m: float | None = None,
    local_date: str | None = None,
    policy: MatchPolicy = MatchPolicy(),
    exclude_activity_id: str | None = None,
    allow_create: bool = False,
) -> MatchDecision:
    """Resolve one imported row to an activity, a review set or a create.

    The ladder is deliberate and shared by every source:

    1. temporal overlap (with the source's contained-segment rule);
    2. distance agreement, when both sides carry a distance;
    3. a same-day exact twin, when the window was rejected but duration and
       distance match to a hair;
    4. an ambiguous review item, never a guess;
    5. creation only when the source profile and the caller allow it.

    Runalyze passes ``exact_twin=False`` because its review path owns the
    sheet-duplicate refinement; the temporal and distance steps are the same.
    """
    if not started_at_utc:
        return MatchDecision(None, "no_start")

    if elapsed_s <= 0 and duration_s <= 0:
        return MatchDecision(None, "no_duration")

    matches = ActivityMatcher(connection).find(
        started_at_utc=started_at_utc,
        source=source,
        elapsed_s=elapsed_s,
        duration_s=duration_s,
        exclude_activity_id=exclude_activity_id,
    )
    viable = [
        match
        for match in matches
        if _distance_agrees(connection, distance_m, match, policy)
    ]

    if len(viable) == 1:
        match = viable[0]
        return MatchDecision(
            match.activity_id,
            "matched",
            match.match_method,
            match.confidence,
        )

    if len(viable) > 1:
        return MatchDecision(
            None,
            "ambiguous_match",
            candidates=tuple(viable),
        )

    if policy.exact_twin and distance_m is not None:
        twins = _exact_twins(
            connection,
            local_date=local_date or _local_date(started_at_utc),
            duration_s=duration_s or elapsed_s,
            distance_m=distance_m,
            policy=policy,
        )
        if len(twins) == 1:
            return MatchDecision(
                twins[0].activity_id,
                "exact_twin",
                "exact_twin",
                1.0,
            )
        if len(twins) > 1:
            return MatchDecision(
                None,
                "ambiguous_match",
                candidates=tuple(twins),
            )

    if allow_create:
        return MatchDecision(None, "create")

    reason = "distance_mismatch" if matches else "no_temporal_match"
    return MatchDecision(None, reason, candidates=tuple(matches))


def _match_mode(source: str) -> str:
    try:
        return source_profile(source).match
    except KeyError:
        return "contained_fit" if source == "fit" else "temporal"


def _distance_agrees(
    connection: sqlite3.Connection,
    distance_m: float | None,
    match: MatchCandidate,
    policy: MatchPolicy,
) -> bool:
    if distance_m is None:
        return True

    row = connection.execute(
        "SELECT sport, distance_m FROM activities WHERE id = ?",
        (match.activity_id,),
    ).fetchone()
    if row is None:
        return False
    if row["sport"] in NO_DISTANCE_SPORTS:
        return True

    stored = float(row["distance_m"] or 0.0)
    if stored <= 0:
        return True

    tolerance = max(
        policy.distance_m,
        policy.distance_ratio * max(float(distance_m), stored),
    )
    return abs(float(distance_m) - stored) <= tolerance


def _exact_twins(
    connection: sqlite3.Connection,
    *,
    local_date: str | None,
    duration_s: float,
    distance_m: float,
    policy: MatchPolicy,
) -> list[MatchCandidate]:
    """Same-day rows whose duration and distance match to a hair."""
    if not local_date or duration_s <= 0:
        return []

    rows = connection.execute(
        """
        SELECT id, duration_s, distance_m
        FROM activities
        WHERE local_date = ? AND excluded_at IS NULL
        """,
        (local_date,),
    ).fetchall()

    twins: list[MatchCandidate] = []
    for row in rows:
        stored_duration = float(row["duration_s"] or 0.0)
        stored_distance = row["distance_m"]
        if stored_duration <= 0 or stored_distance is None:
            continue
        if abs(stored_duration - duration_s) > policy.exact_duration_s:
            continue
        if abs(float(stored_distance) - distance_m) > policy.exact_distance_m:
            continue
        twins.append(
            MatchCandidate(
                activity_id=row["id"],
                match_method="exact_twin",
                confidence=1.0,
                overlap_s=0.0,
                shorter_ratio=1.0,
            )
        )
    return twins


def _local_date(started_at_utc: str) -> str | None:
    moment = parse_utc(started_at_utc)
    return moment.date().isoformat() if moment is not None else None


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
