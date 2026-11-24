"""Deterministic synthetic training database for the public demo.

The generator never reads the canonical database or any personal data. It
writes a fresh SQLite file through ``TrainingWriter`` so the demo exercises
the same schema and read paths as a real import: activities, intervals, zone
times, wellness, planned events, races, and equipment.

The athlete is invented and follows a story: four weeks of continuous
running, a first 5k, a rest week, a classical build to 10k and half marathon,
an injury and a careful return, a marathon block and a first marathon, six
boom-and-bust weeks, then a threshold-focused Norwegian singles block with
double-threshold days and a long sustainable climb.

One fitness curve (a 5k pace plus an endurance profile per distance) drives
every race time and training pace, and a separate watch curve drives VO2max.
The estimate only updates on a quality or long run, holds between them, sits
on a 0.1 grid, drops through the injury and the bust and climbs more slowly
once the threshold block replaces intervals. Easy and long runs stay in zones
1-2, workouts carry the hard zones, and rides carry no running VO2max. The
future plan copies the last four complete weeks.
"""

from __future__ import annotations

import calendar
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from hobbyjogging_core import open_database
from hobbyjogging_core.db import TrainingWriter
from hobbyjogging_core.model import EventZoneTime, Interval

DEMO_SOURCE = "demo"
DEFAULT_MONTHS = 48
DEFAULT_SEED = 7
ZONE_KIND = "pace"
# The invented athlete's measured maximum; session max HR stays below it.
_ATHLETE_MAX_HR = 192.0

_RUN_SPORTS = {"run", "trail_run"}
_ILLNESS_DAYS = 5
_TRAVEL_DAYS = 7

_EASY_NAMES = (
    "Easy",
    "Morning easy",
    "Easy + strides",
    "Recovery jog",
    "Neighbourhood loop",
)
_CROSS_NAMES = (
    "Easy ride",
    "Spin",
    "Cross-training ride",
)
_LONG_NAMES = (
    "Long run",
    "Sunday long run",
    "Trail long run",
    "Long steady run",
)


@dataclass(frozen=True)
class DemoSummary:
    """What the generator wrote."""

    path: Path
    activities: int
    wellness_days: int
    events: int
    equipment: int
    periods: int


def generate_demo_database(
    path: str | Path,
    *,
    months: int = DEFAULT_MONTHS,
    seed: int = DEFAULT_SEED,
    today: date | None = None,
    with_review_items: bool = False,
    force: bool = False,
) -> DemoSummary:
    """Write a complete synthetic database to ``path``.

    ``path`` is always explicit; the canonical ``HOBBYJOGGING_DB`` is never
    used. An existing file is refused unless ``force`` is true.
    """
    if months <= 0:
        raise ValueError("months must be positive")
    if months > 60:
        raise ValueError("months must be 60 or less")

    target = Path(path).expanduser()

    if target.exists():
        if not force:
            raise FileExistsError(
                f"{target} already exists; pass --force to overwrite"
            )
        for suffix in ("", "-wal", "-shm"):
            Path(f"{target}{suffix}").unlink(missing_ok=True)

    today = today or date.today()
    rng = random.Random(seed)
    start = _months_before(today, months)
    connection = open_database(target)
    writer = TrainingWriter(connection)

    try:
        connection.execute("BEGIN")
        result = _write_demo(
            writer,
            rng,
            start,
            today,
            with_review_items=with_review_items,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return DemoSummary(
        path=target,
        activities=result["activities"],
        wellness_days=result["wellness_days"],
        events=result["events"],
        equipment=result["equipment"],
        periods=result["periods"],
    )


def _write_demo(
    writer: TrainingWriter,
    rng: random.Random,
    start: date,
    today: date,
    *,
    with_review_items: bool,
) -> dict[str, int]:
    equipment = _write_equipment(writer, start, today)
    _write_devices(writer, start, today)
    activities = _write_activities(writer, rng, start, today)
    _write_wellness(writer, activities, start, today, rng)
    events = _write_events(writer, activities, today)
    periods = _write_periods(writer, start, today)
    _write_thresholds(writer, start, today)
    _write_race_results(writer, activities)

    if with_review_items:
        _write_review_items(writer, activities)

    return {
        "activities": len(activities),
        "wellness_days": (today - start).days + 1,
        "events": events,
        "equipment": equipment,
        "periods": periods,
    }


_DEMO_SEASONS = (
    (0, 30 * 7 - 1, "Base and classics"),
    (30 * 7, 60 * 7 - 1, "Marathon build"),
    (60 * 7, None, "Norwegian block"),
)


def _write_devices(writer, start: date, today: date) -> None:
    """Write a small Garmin device history for the story.

    The watches carry the FIT shape (manufacturer and product, no name) and
    the bike computer the provider fallback shape (name only), so the demo
    exercises both label paths.
    """
    mid = start + timedelta(days=int(max((today - start).days, 1) * 0.45))

    for device_id, shape, acquired, retired in (
        (
            "demo-fr645",
            {"manufacturer": "garmin", "product": "fr645"},
            start - timedelta(days=100),
            mid,
        ),
        (
            "demo-enduro",
            {"manufacturer": "garmin", "product": "enduro"},
            mid,
            None,
        ),
        (
            "demo-edge",
            {"name": "Garmin Edge 540"},
            start - timedelta(days=100),
            None,
        ),
    ):
        writer.upsert_device(
            device_id,
            **shape,
            acquired_on=acquired,
            retired_on=retired,
        )


def _write_thresholds(writer, start: date, today: date) -> None:
    """Write a plausible run threshold series for the story."""
    span = max((today - start).days, 1)
    rows = []

    # A threshold sits slower than 10k race pace; the story's 10k is ~3:42.
    for share, pace in (
        (0.0, 4.30),
        (0.35, 4.35),
        (0.72, 4.40),
        (1.0, 4.45),
    ):
        day = start + timedelta(days=int(span * share))
        rows.append({
            "effective_from": day.isoformat(),
            "sport": "run",
            "max_hr": _ATHLETE_MAX_HR,
            "lthr": 174.0,
            "threshold_pace_mps": pace,
        })

    writer.replace_athlete_thresholds(rows, source="demo")


def _write_race_results(writer, activities: list[dict]) -> None:
    """Give the latest demo races an official result and placement."""
    races = [
        activity
        for activity in activities
        if "race" in activity["methods"]
    ]
    races.sort(key=lambda activity: activity["day"])
    placements = (
        (12, 340, 3, 54),
        (8, None, 4, 87),
        (21, 512, None, None),
    )
    official_names = ("Lakeside 5k", "Old Town 10k", "Year-End 10k")

    for activity, placement, official_name in zip(
        races[-3:],
        placements,
        official_names,
    ):
        values = activity["values"]
        (
            place_total,
            participants_total,
            place_ageclass,
            participants_ageclass,
        ) = placement
        writer.upsert_race_result(
            activity["id"],
            source="demo",
            name=official_name,
            official_distance_m=round(values["distance_m"], 1),
            official_time_s=round(values["duration_s"]),
            officially_measured=True,
            place_total=place_total,
            participants_total=participants_total,
            place_ageclass=place_ageclass,
            participants_ageclass=participants_ageclass,
            status="completed",
        )


def _write_periods(writer, start: date, today: date) -> int:
    """Write the story's seasons and illness ranges as manual periods."""
    written = 0

    for index, (first, last, label) in enumerate(_DEMO_SEASONS):
        start_date = start + timedelta(days=first)

        if start_date > today:
            continue

        end_date = (
            start + timedelta(days=last) if last is not None else None
        )

        if end_date is not None and end_date > today:
            end_date = None

        writer.upsert_training_period(
            f"demo:season:{index}",
            kind="season",
            label=label,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat() if end_date else None,
        )
        written += 1

    injury_start = start + timedelta(days=_INJURY_DAYS.start)
    injury_end = start + timedelta(days=_INJURY_DAYS.stop - 1)

    if injury_start <= today:
        writer.upsert_training_period(
            "demo:illness:injury",
            kind="illness",
            label="Injury",
            start_date=injury_start.isoformat(),
            end_date=min(injury_end, today).isoformat(),
        )
        written += 1

    # A recent cold keeps an illness band inside the recovery window.
    cold_start = today - timedelta(days=120)
    cold_end = cold_start + timedelta(days=4)

    if cold_start >= start:
        writer.upsert_training_period(
            "demo:illness:cold",
            kind="illness",
            label="Chest cold",
            start_date=cold_start.isoformat(),
            end_date=cold_end.isoformat(),
        )
        written += 1

    return written


def _months_before(day: date, months: int) -> date:
    year = day.year - months // 12
    month = day.month - months % 12

    while month <= 0:
        month += 12
        year -= 1

    return date(
        year,
        month,
        min(day.day, calendar.monthrange(year, month)[1]),
    )


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


@dataclass(frozen=True)
class Fitness:
    """The athlete's form as race and training paces, in seconds per km."""

    p5k: float
    ten_k: float
    half: float
    marathon: float

    def race_pace(self, distance_m: float) -> float:
        """Expected race pace for a distance, from the 5k pace."""
        km = distance_m / 1000

        if km <= 5.5:
            return self.p5k
        if km <= 12.0:
            return self.p5k * self.ten_k
        if km <= 25.0:
            return self.p5k * self.half

        return self.p5k * self.marathon

    @property
    def easy(self) -> float:
        return self.p5k * 1.36

    @property
    def recovery(self) -> float:
        return self.p5k * 1.44

    @property
    def long(self) -> float:
        return self.p5k * 1.32

    @property
    def threshold(self) -> float:
        return self.p5k * 1.07


# (week, 5k pace, 10k factor, half factor, marathon factor) over the log.
# The 5k pace improves through the story; the factors are the athlete's
# endurance profile, which gets flatter as the threshold work piles up.
_FITNESS_POINTS = (
    (0.0, 250.0, 1.06, 1.20, 1.40),
    (3.0, 246.0, 1.05, 1.18, 1.38),
    (5.0, 247.0, 1.05, 1.18, 1.38),
    (15.0, 233.0, 1.03, 1.16, 1.35),
    (24.0, 230.0, 1.03, 1.17, 1.33),
    (26.0, 235.0, 1.04, 1.18, 1.34),
    (30.0, 236.0, 1.04, 1.18, 1.34),
    (35.0, 233.0, 1.03, 1.16, 1.31),
    (54.0, 228.0, 1.03, 1.15, 1.28),
    (57.0, 242.0, 1.05, 1.20, 1.34),
    (60.0, 234.0, 1.04, 1.17, 1.31),
    (61.0, 232.0, 1.03, 1.16, 1.29),
    (90.0, 226.0, 1.03, 1.12, 1.22),
    (120.0, 220.0, 1.03, 1.09, 1.16),
    (150.0, 219.0, 1.03, 1.09, 1.16),
    (180.0, 217.0, 1.03, 1.09, 1.15),
    (208.0, 216.0, 1.03, 1.09, 1.15),
)


def _fitness(day: date, start: date) -> Fitness:
    """Interpolated fitness for a day, so paces move smoothly."""
    week = (day - start).days / 7.0
    points = _FITNESS_POINTS

    if week <= points[0][0]:
        return Fitness(*points[0][1:])
    if week >= points[-1][0]:
        return Fitness(*points[-1][1:])

    for (left, *before), (right, *after) in zip(points, points[1:]):
        if left <= week <= right:
            share = (week - left) / (right - left)
            values = [
                old + (new - old) * share
                for old, new in zip(before, after)
            ]
            return Fitness(*values)

    return Fitness(*points[-1][1:])


# (week, VO2max) — one curve for the story. It falls through the 10-day
# injury and the boom-bust, and climbs more slowly once the Norwegian block
# replaces intervals with threshold work.
_VO2MAX_POINTS = (
    (0.0, 42.6),
    (3.0, 43.4),
    (5.0, 43.2),
    (15.0, 46.2),
    (24.0, 47.8),
    (25.0, 47.6),
    (26.5, 46.2),
    (30.0, 47.0),
    (35.0, 47.8),
    (54.0, 48.6),
    (55.5, 48.2),
    (57.0, 46.4),
    (60.0, 47.0),
    (61.0, 47.5),
    (90.0, 48.8),
    (120.0, 49.8),
    (140.0, 50.4),
    (150.0, 50.6),
    (180.0, 51.0),
    (208.0, 51.4),
)


def _vo2max_value(day: date, start: date) -> float:
    """The watch's VO2max estimate for a day, on a 0.1 grid."""
    week = (day - start).days / 7.0
    points = _VO2MAX_POINTS

    if week <= points[0][0]:
        value = points[0][1]
    elif week >= points[-1][0]:
        value = points[-1][1]
    else:
        value = points[-1][1]

        for (left, before), (right, after) in zip(points, points[1:]):
            if left <= week <= right:
                share = (week - left) / (right - left)
                value = before + (after - before) * share
                break

    return round(value, 1)


def _phase_for_week(week: int) -> str:
    if week <= 3:
        return "intro"
    if week == 4:
        return "rest"
    if week <= 9:
        return "classic"
    if week <= 24:
        return "build"
    if week <= 25:
        return "injury"
    if week <= 29:
        return "resume"
    if week <= 54:
        return "marathon"
    if week <= 60:
        return "bust"

    return "norwegian"


# (week, name, distance) — raced on the Sunday; times come from the curve.
_RACES = (
    (3, "First 5k", 5000.0),
    (15, "First 10k", 10000.0),
    (24, "First Half", 21097.5),
    (54, "First Marathon", 42195.0),
    (57, "Comeback 10k", 10000.0),
    (60, "Rebuild 5k", 5000.0),
    (90, "Second Half", 21097.5),
    (120, "Second 10k", 10000.0),
    (140, "Second Marathon", 42195.0),
    (150, "Third Half", 21097.5),
    (180, "PB 5k", 5000.0),
    (190, "PB 10k", 10000.0),
    (205, "Recent 10k", 10000.0),
)

# The first rest week and the injury after the half marathon.
_REST_DAYS = range(28, 35)
_INJURY_DAYS = range(175, 185)


def _write_activities(
    writer: TrainingWriter,
    rng: random.Random,
    start: date,
    today: date,
) -> list[dict]:
    """Generate the story: beginner weeks, classics, injury, marathon, doubles."""
    generated: list[dict] = []
    monday = _monday(start)
    start_monday = monday
    shoe_periods = _shoe_periods(start, today)
    device_mid = start + timedelta(
        days=int(max((today - start).days, 1) * 0.45)
    )

    def device_for(day: date, sport: str) -> str:
        if sport == "ride":
            return "demo-edge"
        return "demo-fr645" if day < device_mid else "demo-enduro"

    race_days = {
        start_monday + timedelta(weeks=week, days=6): (name, distance_m)
        for week, name, distance_m in _RACES
    }
    blocked = {
        start_monday + timedelta(days=offset)
        for offset in (*_REST_DAYS, *_INJURY_DAYS)
    }
    race_weeks = {week for week, _name, _distance in _RACES}
    long_race_weeks = {
        week for week, _name, distance in _RACES if distance >= 21000
    }

    while monday <= today:
        week = (monday - start_monday).days // 7
        phase = _phase_for_week(week)
        slots: dict[date, int] = {}
        plan = _weekly_plan(phase, week, rng)

        # Race weeks stay easy; a half or marathon also gets a taper week.
        if week in race_weeks:
            plan = [(1, "easy"), (3, "easy"), (6, "easy")]
        elif week + 1 in long_race_weeks:
            plan = [(1, "easy"), (3, "easy"), (5, "easy")]

        if week == 20:
            # One unstructured fartlek, so the demo exercises the category
            # that no other session in the story carries.
            plan = [
                (weekday, "fartlek" if kind == "intervals" else kind)
                for weekday, kind in plan
            ]

        update_days = {
            monday + timedelta(days=weekday)
            for weekday, kind in plan
            if kind in (
                "long",
                "tempo",
                "intervals",
                "subthreshold",
                "fartlek",
            )
        }

        for weekday, kind in plan:
            day = monday + timedelta(days=weekday)

            if not (start <= day <= today):
                continue
            if day in blocked or day in race_days:
                continue

            slot = slots.get(day, 0)
            slots[day] = slot + 1
            fitness = _fitness(day, start)
            activity = _make_session(
                rng,
                day,
                kind,
                fitness=fitness,
                phase=phase,
                week=week,
                vo2max_value=(
                    _vo2max_value(day, start) if day in update_days else None
                ),
                index=len(generated),
                shoe_periods=shoe_periods,
                slot=slot,
            )
            activity["values"]["device_id"] = device_for(
                day,
                activity["sport"],
            )
            _write_activity(writer, activity)
            generated.append(activity)

        monday += timedelta(days=7)

    for day in sorted(race_days):
        if not (start <= day <= today):
            continue

        name, distance_m = race_days[day]
        fitness = _fitness(day, start)
        duration = (
            distance_m
            / 1000
            * fitness.race_pace(distance_m)
            * rng.uniform(0.995, 1.01)
        )
        activity = _make_race(
            day,
            name,
            distance_m,
            duration,
            index=len(generated),
            shoe_periods=shoe_periods,
            vo2max_value=_vo2max_value(day, start),
        )
        activity["values"]["device_id"] = device_for(day, "run")
        _write_activity(writer, activity)
        generated.append(activity)

    return generated


def _make_race(
    day: date,
    name: str,
    distance_m: float,
    duration_s: float,
    *,
    index: int,
    shoe_periods: list[tuple[date, date, str]],
    vo2max_value: float,
) -> dict:
    """Build one completed race so the demo has results and PBs."""
    activity_id = f"demo-{day.isoformat()}-race-{index:04d}"
    pace = duration_s / distance_m * 1000
    load = round(duration_s / 60 * 1.05, 1)
    started = datetime.combine(
        day,
        time(9, 30),
        tzinfo=timezone(timedelta(minutes=60)),
    ).astimezone(timezone.utc)
    target = "marathon" if distance_m > 15000 else "speed"

    return {
        "id": activity_id,
        "day": day,
        "sport": "run",
        "name": name,
        "values": {
            "local_date": day.isoformat(),
            "started_at_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tz_offset_min": 60,
            "sport": "run",
            "name": name,
            "description": "Demo race. Even effort, controlled finish.",
            "duration_s": duration_s,
            "elapsed_s": duration_s,
            "moving_s": duration_s,
            "distance_m": distance_m,
            "avg_hr": 176,
            "max_hr": 188,
            "training_load": load,
            "rpe": 5,
            "feel": 1,
            "intensity": 0.95,
            "vo2max_garmin": round(vo2max_value, 1),
        },
        "methods": ["race"],
        "targets": [target],
        "intervals": [],
        "zone_times": _zone_times(duration_s, (0.05, 0.1, 0.5, 0.35)),
        "equipment_id": _shoe_for(day, "run", shoe_periods),
        "kind": "quality",
        "load": load,
    }


def _weekly_plan(phase: str, week: int, rng: random.Random) -> list[tuple[int, str]]:
    """(weekday, kind) pairs for one week of the story."""
    if phase == "intro":
        return [(1, "easy"), (3, "easy"), (5, "easy")]

    if phase in ("rest", "injury"):
        return []

    if phase == "resume":
        return [
            (1, "easy"),
            (3, "easy"),
            (5, "easy"),
            (6, "long"),
        ]

    if phase == "bust":
        return [(1, "easy"), (3, "easy"), (5, "easy")]

    if phase == "classic":
        return [
            (0, "intervals"),
            (2, "tempo"),
            (4, "cross" if week % 4 == 3 else "easy"),
            (6, "long"),
        ]

    if phase == "marathon" and week % 4 == 3:
        # Every fourth week backs off after a block of work.
        return [(1, "easy"), (3, "easy"), (5, "cross")]

    if phase in ("build", "marathon"):
        return [
            (0, "intervals"),
            (1, "easy"),
            (3, "tempo"),
            (4, "cross" if week % 4 == 3 else "easy"),
            (6, "long"),
        ]

    # Norwegian singles: two double-threshold days, easy runs around them.
    plan = [
        (0, "easy"),
        (1, "subthreshold"),
        (1, "subthreshold"),
        (3, "subthreshold"),
        (3, "subthreshold"),
        (4, "easy"),
        (6, "long"),
    ]

    if week % 2:
        plan.append((2, "easy"))

    return plan


def _make_session(
    rng: random.Random,
    day: date,
    kind: str,
    *,
    fitness: Fitness,
    phase: str,
    week: int,
    vo2max_value: float | None,
    index: int,
    shoe_periods: list[tuple[date, date, str]],
    slot: int = 0,
) -> dict:
    """Build one activity's values, intervals, and summary metadata."""
    activity_id = f"demo-{day.isoformat()}-{index:04d}"
    sport = "run"
    intervals: list[Interval] = []
    progress = min(week / 208.0, 1.0)

    if kind == "cross":
        name = rng.choice(_CROSS_NAMES)
        duration = rng.choice((45, 55, 60)) * 60.0
        pace = None
        avg_hr = rng.randint(118, 132)
        methods = ["continuous"]
        targets = ["other"]
        zone_shares = (0.35, 0.45, 0.15, 0.05)
        distance_m = 0.0
        sport = "ride"
        vo2max_value = None
    elif kind == "long":
        name = rng.choice(_LONG_NAMES)
        duration = _long_minutes(phase, rng) * 60.0
        duration *= _volume_ramp(phase, week)
        pace = fitness.long + rng.uniform(-5, 5)
        avg_hr = 138 - 6 * progress + rng.randint(-3, 3)
        methods = ["long_run"]
        targets = (
            ["marathon"]
            if phase in ("marathon", "norwegian")
            else ["base"]
        )
        zone_shares = (0.2, 0.8, 0.0, 0.0)
        distance_m = duration / pace * 1000
        if "Trail" in name and rng.random() < 0.5:
            sport = "trail_run"
    elif kind == "fartlek":
        name = "Fartlek"
        duration = rng.choice((45, 50, 55)) * 60.0
        pace = (
            fitness.threshold + fitness.easy
        ) / 2 + rng.uniform(-6, 6)
        avg_hr = 156 - 4 * progress + rng.randint(-3, 3)
        methods = ["fartlek"]
        targets = ["vo2max"]
        zone_shares = (0.25, 0.35, 0.25, 0.15)
        distance_m = duration / pace * 1000
    elif kind == "tempo":
        name = "Tempo run"
        duration = rng.choice((30, 35, 40)) * 60.0
        pace = fitness.threshold + rng.uniform(2, 10)
        avg_hr = 160 - 6 * progress + rng.randint(-3, 3)
        methods = ["continuous"]
        targets = ["threshold"]
        zone_shares = (0.08, 0.27, 0.40, 0.25)
        distance_m = duration / pace * 1000
    elif kind in ("intervals", "subthreshold"):
        if kind == "intervals":
            name, reps, rep_s, factor, recovery_s, target = (
                _interval_session(rng, phase)
            )
            rep_hr = 174 if target == "vo2max" else 170
            warmup_s = rng.choice((720, 900))
            cooldown_s = rng.choice((480, 600))
        else:
            name, reps, rep_s, factor, recovery_s = _subthreshold_session(rng)
            rep_hr = 164
            warmup_s = rng.choice((900, 1080))
            cooldown_s = rng.choice((600, 720))
            target = "subthreshold"

        rep_pace = fitness.p5k * factor
        group = f"{activity_id}-work"
        warmup = _interval(
            "WARMUP",
            warmup_s,
            fitness.easy + rng.uniform(-5, 5),
            130,
            group,
        )
        work = [
            _interval(
                "WORK",
                rep_s,
                rep_pace + rng.uniform(-3, 3),
                rep_hr - 4 * progress,
                group,
            )
            for _ in range(reps)
        ]
        recoveries = [
            _interval(
                "RECOVERY",
                recovery_s,
                fitness.recovery + rng.uniform(-5, 5),
                132,
                group,
            )
            for _ in range(reps - 1)
        ]
        cooldown = _interval(
            "COOLDOWN",
            cooldown_s,
            fitness.easy + rng.uniform(-5, 5),
            128,
            group,
        )
        intervals = [warmup]

        for rep in range(reps):
            intervals.append(work[rep])
            if rep < reps - 1:
                intervals.append(recoveries[rep])

        intervals.append(cooldown)
        duration = sum(item.duration_s for item in intervals)
        distance_m = sum(item.distance_m for item in intervals)
        pace = duration / distance_m * 1000
        avg_hr = rep_hr - 4 - 4 * progress
        methods = ["intervals"]
        targets = [target]
        zone_shares = (0.18, 0.22, 0.35, 0.25)
    elif kind == "recovery":
        name = "Recovery jog"
        duration = rng.randint(30, 40) * 60.0
        pace = fitness.recovery + rng.uniform(-4, 4)
        avg_hr = 118 - 4 * progress + rng.randint(-3, 3)
        methods = ["continuous"]
        targets = ["recovery"]
        zone_shares = (0.45, 0.55, 0.0, 0.0)
        distance_m = duration / pace * 1000
    else:
        if phase == "intro":
            name = rng.choice(
                ("Easy", "Morning easy", "Neighbourhood loop")
            )
        else:
            name = rng.choice(_EASY_NAMES)

        duration = _easy_minutes(phase, rng) * 60.0
        duration *= _volume_ramp(phase, week)
        pace = fitness.easy + rng.uniform(-6, 6)
        avg_hr = 140 - 8 * progress + rng.randint(-4, 4)
        methods = ["continuous"]

        if "strides" in name:
            methods.append("strides")

        targets = ["base"]
        zone_shares = (0.35, 0.65, 0.0, 0.0)
        distance_m = duration / pace * 1000

    load = _training_load(kind, duration, phase)
    rpe = _rpe(kind, rng)
    feel = _feel(rng)
    intensity = load / max(duration / 60, 1) / 100

    started = datetime.combine(
        day,
        _start_time(kind, slot),
        tzinfo=timezone(timedelta(minutes=60)),
    ).astimezone(timezone.utc)
    equipment_id = _shoe_for(day, sport, shoe_periods)

    description = _description(kind, phase)
    return {
        "id": activity_id,
        "day": day,
        "sport": sport,
        "name": name,
        "values": {
            "local_date": day.isoformat(),
            "started_at_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tz_offset_min": 60,
            "sport": sport,
            "name": name,
            "description": description,
            "duration_s": duration,
            "elapsed_s": duration + rng.choice((0, 20, 45)),
            "moving_s": duration,
            "distance_m": round(distance_m, 1),
            "avg_hr": avg_hr,
            "max_hr": min(
                _ATHLETE_MAX_HR,
                round(avg_hr + rng.randint(6, 14)),
            ),
            "training_load": round(load, 1),
            "rpe": rpe,
            "feel": feel,
            "intensity": round(min(max(intensity, 0.45), 0.95), 2),
            "vo2max_garmin": (
                round(vo2max_value, 1)
                if vo2max_value is not None
                else None
            ),
        },
        "methods": methods,
        "targets": targets,
        "intervals": intervals,
        "zone_times": _zone_times(duration, zone_shares),
        "equipment_id": equipment_id,
        "kind": "quality" if kind in ("tempo", "intervals", "subthreshold") else kind,
        "load": load,
    }


def _volume_ramp(phase: str, week: int) -> float:
    """Build volume after a break and ramp the Norwegian block."""
    if phase == "resume":
        return min(1.0, 0.6 + 0.13 * max(0, week - 26))

    if phase != "norwegian":
        return 1.0

    since = max(0, week - 61)

    return min(1.0, 0.45 + 0.55 * since / 16)


def _easy_minutes(phase: str, rng: random.Random) -> int:
    low, high = {
        "intro": (30, 38),
        "classic": (38, 50),
        "build": (45, 60),
        "resume": (25, 40),
        "marathon": (45, 65),
        "bust": (30, 45),
        "norwegian": (50, 70),
    }.get(phase, (40, 55))

    return rng.randint(low, high)


def _long_minutes(phase: str, rng: random.Random) -> int:
    low, high = {
        "classic": (60, 80),
        "build": (80, 105),
        "marathon": (110, 160),
        "bust": (50, 70),
        "norwegian": (110, 150),
    }.get(phase, (60, 80))

    return rng.randint(low, high)


def _interval_session(rng: random.Random, phase: str):
    options = [
        ("5x3' 5k pace", 5, 180, 1.00, 120, "speed"),
        ("4x5' 5k pace", 4, 300, 1.02, 150, "speed"),
        ("6x2' VO2max", 6, 120, 0.96, 90, "vo2max"),
        ("5x3' VO2max", 5, 180, 0.97, 120, "vo2max"),
    ]

    if phase == "classic":
        return rng.choice((options[0], options[3]))

    return rng.choice(options[:3])


def _subthreshold_session(rng: random.Random):
    return rng.choice((
        ("6x3' subT", 6, 180, 1.09, 60),
        ("5x6' subT", 5, 360, 1.06, 90),
        ("4x8' subT", 4, 480, 1.06, 90),
        ("3x10' subT", 3, 600, 1.05, 120),
        ("2x15' subT", 2, 900, 1.04, 180),
    ))


def _training_load(kind: str, duration_s: float, phase: str) -> float:
    factor = {
        "easy": 0.72,
        "recovery": 0.55,
        "long": 0.86,
        "cross": 0.62,
        "quality": 1.05,
        "tempo": 1.02,
        "fartlek": 1.0,
        "intervals": 1.08,
        "subthreshold": 1.06,
    }.get(kind, 0.8)

    if phase in ("marathon", "norwegian") and kind == "long":
        factor += 0.04

    return duration_s / 60 * factor


def _rpe(kind: str, rng: random.Random) -> float:
    if kind in ("tempo", "intervals", "subthreshold", "quality"):
        return float(rng.choice((6, 7, 7, 8)))
    if kind == "long":
        return float(rng.choice((5, 6, 6, 7)))
    if kind == "recovery":
        return float(rng.choice((1, 2, 2)))
    return float(rng.choice((2, 3, 3, 4)))


def _feel(rng: random.Random) -> int:
    return rng.choice((1, 2, 2, 3, 3, 3, 4, 4, 5))


def _start_time(kind: str, slot: int = 0) -> time:
    if slot:
        return time(17, 0)
    if kind in ("long", "cross"):
        return time(9, 30)
    return time(16, 45)


def _interval(
    interval_type: str,
    duration_s: float,
    pace_s_per_km: float,
    avg_hr: float,
    group_id: str,
) -> Interval:
    return Interval(
        group_id=group_id,
        type=interval_type,
        duration_s=float(duration_s),
        distance_m=round(duration_s / pace_s_per_km * 1000, 1),
        avg_hr=round(avg_hr),
        max_hr=round(avg_hr + 8),
    )


def _zone_times(total_s: float, shares: tuple[float, ...]) -> list[float]:
    parts = [round(total_s * share) for share in shares]
    parts[0] += round(total_s) - sum(parts)
    return [float(part) if part > 0 else 0.0 for part in parts]


def _description(kind: str, phase: str) -> str:
    if kind in ("tempo", "intervals", "subthreshold", "fartlek"):
        return (
            "Quality session in the invented plan.\n"
            f"Block: {phase}. Reps on the road, recoveries easy."
        )
    if kind == "long":
        return (
            "Steady long run.\n"
            "Fuel every 40 minutes; keep the last third controlled."
        )

    return "Relaxed running. Keep it conversational."


def _shoe_periods(start: date, today: date) -> list[tuple[date, date, str]]:
    span = max((today - start).days, 1)
    first = start
    second = start + timedelta(days=int(span * 0.35))
    third = start + timedelta(days=int(span * 0.72))
    return [
        (first, second, "demo-shoe-1"),
        (second, third, "demo-shoe-2"),
        (third, today, "demo-shoe-3"),
    ]


def _shoe_for(
    day: date,
    sport: str,
    periods: list[tuple[date, date, str]],
) -> str | None:
    if sport == "ride":
        return "demo-bike-1"
    if sport == "trail_run":
        return "demo-shoe-4"

    for start, end, equipment_id in periods:
        if start <= day < end:
            return equipment_id

    return periods[-1][2]


_MONTH_TEMPERATURE_C = (4, 5, 9, 13, 18, 22, 24, 23, 19, 13, 8, 5)


def _write_weather(writer: TrainingWriter, activity: dict) -> None:
    """Seasonal conditions, with a few missing days like a real log."""
    day = activity["day"]
    ordinal = day.toordinal()

    if ordinal % 37 == 0:
        return

    writer.upsert_activity_weather(
        activity["id"],
        source=DEMO_SOURCE,
        temp_c=float(_MONTH_TEMPERATURE_C[day.month - 1] + ordinal % 5 - 2),
        wind_speed_ms=round(1.5 + (ordinal % 9) * 0.5, 1),
    )


def _write_activity(writer: TrainingWriter, activity: dict) -> None:
    writer.upsert_activity(
        activity["id"],
        activity["values"],
        source=DEMO_SOURCE,
        source_record_id=None,
    )
    writer.set_activity_zone_times(
        activity["id"],
        ZONE_KIND,
        activity["zone_times"],
    )
    writer.set_activity_zone_times(
        activity["id"],
        "hr",
        activity["zone_times"],
    )
    writer.replace_activity_workout_methods(
        activity["id"],
        activity["methods"],
        source=DEMO_SOURCE,
    )
    writer.replace_activity_workout_targets(
        activity["id"],
        activity["targets"],
        source=DEMO_SOURCE,
    )
    _write_weather(writer, activity)

    if activity["intervals"]:
        writer.replace_activity_intervals(
            activity["id"],
            activity["intervals"],
            source="intervals",
        )

    if activity["equipment_id"]:
        writer.link_activity_equipment(
            activity["id"],
            activity["equipment_id"],
            source=DEMO_SOURCE,
        )


def _write_wellness(
    writer: TrainingWriter,
    activities: list[dict],
    start: date,
    today: date,
    rng: random.Random,
) -> None:
    loads: dict[date, float] = {}

    for activity in activities:
        loads[activity["day"]] = (
            loads.get(activity["day"], 0.0) + activity["load"]
        )

    illness_start = today - timedelta(days=250)
    travel_start = today - timedelta(days=90)
    day = start

    while day <= today:
        prior = [
            loads.get(day - timedelta(days=offset), 0.0)
            for offset in range(7)
        ]
        load_7d = sum(prior) / 7
        hrv = 64 - 0.035 * load_7d + rng.gauss(0, 3.5)
        rhr = 47 + 0.01 * load_7d + rng.gauss(0, 1.1)
        sleep = 7.7 * 3600 - 120 * (load_7d / 60) + rng.gauss(0, 1500)

        if illness_start <= day < illness_start + timedelta(_ILLNESS_DAYS):
            hrv -= 16
            rhr += 7
            sleep -= 1.2 * 3600
        elif travel_start <= day < travel_start + timedelta(_TRAVEL_DAYS):
            hrv -= 3
            rhr += 2
            sleep -= 0.8 * 3600

        writer.upsert_wellness(
            local_date=day.isoformat(),
            source_record_id=None,
            hrv=round(min(max(hrv, 28), 85), 1),
            resting_hr=round(min(max(rhr, 42), 62), 1),
            sleep_s=round(min(max(sleep, 5.0 * 3600), 9.5 * 3600)),
        )
        day += timedelta(days=1)


def _plan_templates(activities: list[dict], today: date) -> list[list[dict]]:
    """The last four complete weeks, used as future-plan templates."""
    last_monday = _monday(today) - timedelta(weeks=1)
    weeks = [
        last_monday - timedelta(weeks=offset)
        for offset in range(3, -1, -1)
    ]
    by_week: dict[date, list[dict]] = {week: [] for week in weeks}

    for activity in activities:
        week = _monday(activity["day"])
        if "race" in activity["methods"]:
            continue
        if week in by_week:
            by_week[week].append(activity)

    templates = [
        sorted(by_week[week], key=lambda activity: activity["day"])
        for week in weeks
        if by_week[week]
    ]

    return templates or [activities[-5:]]


def _write_events(
    writer: TrainingWriter,
    activities: list[dict],
    today: date,
) -> int:
    count = 0
    race_days = {
        today + timedelta(weeks=4): (
            "Planned 10k",
            10000.0,
            42 * 60,
            72.0,
        ),
        today + timedelta(weeks=12): (
            "Planned Half Marathon",
            21097.5,
            92 * 60,
            95.0,
        ),
        today + timedelta(weeks=14): (
            "Planned Marathon",
            42195.0,
            185 * 60,
            150.0,
        ),
    }
    race_offsets = sorted(race_days)
    templates = _plan_templates(activities, today)
    monday = _monday(today + timedelta(days=1))
    end = today + timedelta(weeks=16)
    week_index = 0

    while monday <= end:
        template = templates[week_index % len(templates)]
        race_week = any(
            monday <= race <= monday + timedelta(days=6)
            for race in race_offsets
        )

        for index, activity in enumerate(template):
            day = monday + timedelta(days=activity["day"].weekday())

            if day <= today or day > end:
                continue

            if any(
                abs((day - race).days) <= 2
                for race in race_offsets
            ):
                continue

            # Race week keeps the easy sessions and drops the hard/long work.
            if race_week and activity["kind"] in ("quality", "long"):
                continue

            _write_event(
                writer,
                f"demo-event-{day.isoformat()}-{index}",
                day,
                activity["name"],
                (
                    f"Planned {activity['name']}: the same shape as the "
                    "recent training block."
                ),
                activity["values"]["duration_s"],
                activity["values"]["distance_m"],
                activity["load"],
                activity["methods"],
                activity["targets"],
                activity["zone_times"],
                sport=activity["sport"],
                zone_kind=(
                    ZONE_KIND
                    if activity["sport"] in _RUN_SPORTS
                    else "hr"
                ),
            )
            count += 1

        monday += timedelta(days=7)
        week_index += 1

    for day, (name, distance_m, duration_s, load) in race_days.items():
        _write_event(
            writer,
            f"demo-event-{day.isoformat()}-race",
            day,
            name,
            "Demo race. Taper the week before and race by feel.",
            duration_s,
            distance_m,
            load,
            ["race"],
            ["marathon"] if distance_m > 15000 else ["speed"],
            _zone_times(duration_s, (0.1, 0.15, 0.4, 0.35)),
        )
        count += 1

    return count


def _write_event(
    writer: TrainingWriter,
    event_id: str,
    day: date,
    name: str,
    description: str,
    duration_s: float,
    distance_m: float,
    load: float,
    methods: list[str],
    targets: list[str],
    zone_times: list[float],
    *,
    sport: str = "run",
    zone_kind: str = ZONE_KIND,
) -> None:
    writer.upsert_event(
        event_id=event_id,
        local_date=day.isoformat(),
        name=name,
        type=sport,
        source_record_id=None,
        description=description,
        duration_s=round(duration_s),
        distance_m=round(distance_m, 1),
        training_load=round(load, 1),
    )
    writer.replace_event_workout_methods(
        event_id,
        methods,
        source=DEMO_SOURCE,
    )
    writer.replace_event_workout_targets(
        event_id,
        targets,
        source=DEMO_SOURCE,
    )
    writer.set_event_zone_times(
        event_id,
        zone_kind,
        [
            EventZoneTime(
                zone_label=f"Z{index}",
                seconds=seconds,
                zone_index=index,
            )
            for index, seconds in enumerate(zone_times, start=1)
            if seconds
        ],
    )


def _write_equipment(
    writer: TrainingWriter,
    start: date,
    today: date,
) -> int:
    span = max((today - start).days, 1)
    shoes = (
        (
            "demo-shoe-1",
            "Pegasus 39",
            "Nike",
            "Pegasus 39",
            start - timedelta(days=120),
            start + timedelta(days=int(span * 0.35)),
            800000.0,
        ),
        (
            "demo-shoe-2",
            "Clifton 9",
            "Hoka",
            "Clifton 9",
            start + timedelta(days=int(span * 0.35) - 10),
            start + timedelta(days=int(span * 0.72)),
            700000.0,
        ),
        (
            "demo-shoe-3",
            "Adrenaline GTS 23",
            "Brooks",
            "Adrenaline GTS 23",
            start + timedelta(days=int(span * 0.72) - 10),
            None,
            650000.0,
        ),
        (
            "demo-shoe-4",
            "Cascadia 17",
            "Brooks",
            "Cascadia 17",
            start - timedelta(days=200),
            None,
            None,
        ),
    )

    for shoe_id, name, brand, model, acquired, retired, target in shoes:
        writer.upsert_equipment(
            shoe_id,
            type="shoe",
            name=name,
            brand=brand,
            model=model,
            acquired_on=acquired,
            retired_on=retired,
            target_distance_m=target,
            notes="Synthetic demo equipment.",
        )

    writer.upsert_equipment(
        "demo-bike-1",
        type="bike",
        name="Road bike",
        brand="Canyon",
        model="Endurace",
        acquired_on=start - timedelta(days=500),
        notes="Synthetic demo equipment.",
    )
    writer.upsert_equipment(
        "demo-other-1",
        type="other",
        name="Gym membership",
        notes="Synthetic demo equipment.",
    )

    return len(shoes) + 2


def _write_review_items(writer: TrainingWriter, activities: list[dict]) -> None:
    run = next(
        activity
        for activity in activities
        if activity["kind"] == "quality"
    )
    easy = next(
        activity
        for activity in activities
        if activity["kind"] == "easy"
    )

    writer.record_review_item(
        category="field_conflict",
        detail="Demo: average heart rate differs between two devices.",
        fingerprint="demo-field-conflict",
        activity_id=run["id"],
        severity="warn",
    )
    writer.record_review_item(
        category="missing_data",
        detail="Demo: this run has no heart-rate stream.",
        fingerprint="demo-missing-hr",
        activity_id=easy["id"],
        severity="info",
    )
