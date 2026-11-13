"""Deterministic synthetic training database for the public demo.

The generator never reads the canonical database or any personal data. It
writes a fresh SQLite file through ``TrainingWriter`` so the demo exercises
the same schema and read paths as a real import: activities, intervals, zone
times, wellness, planned events, races, and equipment.

The athlete is invented: a periodized 18-month block (base, build, peak,
taper), 4-6 sessions per week, easy runs, long runs, subT/LT1 intervals,
VO2max reps, sustained threshold work, cross-training, and strides. Threshold
pace improves slowly and average HR at pace declines, so the compare and
efficiency views have a plausible trend rather than flat noise. Easy and
long runs stay in zones 1-2, workouts carry the hard zones, VO2max is a slow
Garmin-like daily value, and the future plan copies the last four complete
weeks.
"""

from __future__ import annotations

import calendar
import math
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

_RUN_SPORTS = {"run", "trail_run"}
_ILLNESS_DAYS = 5
_TRAVEL_DAYS = 7

# (name, reps, rep seconds, rep pace s/km, rep HR, recovery seconds,
#  method, target)
_QUALITY_SESSIONS = (
    ("6x3' subT short", 6, 180, 220, 158, 90, "intervals", "subthreshold"),
    ("5x5' subT medium", 5, 300, 228, 162, 120, "intervals", "subthreshold"),
    ("2x8' subT long", 2, 480, 232, 164, 150, "intervals", "subthreshold"),
    ("3x8' LT1", 3, 480, 246, 160, 120, "intervals", "lt1"),
    ("5x3' VO2max", 5, 180, 210, 174, 120, "intervals", "vo2max"),
)

_EASY_NAMES = (
    "Easy",
    "Morning easy",
    "Easy + strides",
    "Recovery jog",
    "Neighbourhood loop",
)
_LONG_NAMES = (
    "Long run",
    "Sunday long run",
    "Trail long run",
    "Long steady run",
)
_CROSS_NAMES = (
    "Easy ride",
    "Spin",
    "Cross-training ride",
)


@dataclass(frozen=True)
class DemoSummary:
    """What the generator wrote."""

    path: Path
    activities: int
    wellness_days: int
    events: int
    equipment: int


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
            months=months,
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
    )


def _write_demo(
    writer: TrainingWriter,
    rng: random.Random,
    start: date,
    today: date,
    *,
    months: int,
    with_review_items: bool,
) -> dict[str, int]:
    equipment = _write_equipment(writer, start, today)
    activities = _write_activities(writer, rng, start, today, months=months)
    _write_wellness(writer, activities, start, today, rng)
    events = _write_events(writer, activities, today)

    if with_review_items:
        _write_review_items(writer, activities)

    return {
        "activities": len(activities),
        "wellness_days": (today - start).days + 1,
        "events": events,
        "equipment": equipment,
    }


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


def _write_activities(
    writer: TrainingWriter,
    rng: random.Random,
    start: date,
    today: date,
    *,
    months: int,
) -> list[dict]:
    """Generate the historical activity log and return its summary rows."""
    generated: list[dict] = []
    monday = _monday(start)
    week_index = 0
    total_weeks = max(1, ((today - monday).days // 7) + 1)

    shoe_periods = _shoe_periods(start, today)

    while monday <= today:
        progress = week_index / total_weeks
        recovery_week = week_index % 4 == 3
        phase = _phase(progress)

        plan: list[tuple[int, str]] = [
            (1, "easy" if recovery_week else "quality"),
            (2, "easy"),
            (3, "quality" if not recovery_week else "easy"),
            (5, "long"),
        ]

        if rng.random() < 0.5:
            plan.append((0, "easy"))
        if rng.random() < 0.5:
            plan.append((4, "cross" if rng.random() < 0.4 else "easy"))
        if rng.random() < 0.35:
            plan.append((6, "recovery"))

        for weekday, kind in plan:
            day = monday + timedelta(days=weekday)

            if not (start <= day <= today):
                continue

            progress = (
                (day - start).days / max((today - start).days, 1)
            )
            activity = _make_session(
                rng,
                day,
                kind,
                phase=phase,
                recovery_week=recovery_week,
                progress=progress,
                vo2max_value=_vo2max_value(day, start, today),
                index=len(generated),
                shoe_periods=shoe_periods,
            )
            _write_activity(writer, activity)
            generated.append(activity)

        monday += timedelta(days=7)
        week_index += 1

    races = (
        ("Spring 5k", 5000.0, 1290.0, 154),
        ("Autumn 5k", 5000.0, 1230.0, 56),
        ("Spring 10k", 10000.0, 2640.0, 126),
        ("Autumn 10k", 10000.0, 2550.0, 35),
        ("City Half", 21097.5, 5760.0, 210),
    )

    for name, distance_m, duration_s, days_ago in races:
        day = today - timedelta(days=days_ago)

        if day < start:
            continue

        activity = _make_race(
            day,
            name,
            distance_m,
            duration_s,
            index=len(generated),
            shoe_periods=shoe_periods,
            vo2max_value=_vo2max_value(day, start, today),
        )
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


def _vo2max_value(day: date, start: date, today: date) -> float:
    """Slow, Garmin-like VO2max trend; the same value all day."""
    progress = (day - start).days / max((today - start).days, 1)
    wave = 0.3 * math.sin(progress * math.tau)

    return round(50.2 + 4.2 * progress + wave, 1)


def _phase(progress: float) -> str:
    if progress < 0.25:
        return "base"
    if progress < 0.75:
        return "build"
    if progress < 0.92:
        return "peak"
    return "taper"


def _make_session(
    rng: random.Random,
    day: date,
    kind: str,
    *,
    phase: str,
    recovery_week: bool,
    progress: float,
    vo2max_value: float,
    index: int,
    shoe_periods: list[tuple[date, date, str]],
) -> dict:
    """Build one activity's values, intervals, and summary metadata."""
    activity_id = f"demo-{day.isoformat()}-{index:04d}"
    sport = "run"
    intervals: list[Interval] = []

    if kind == "cross":
        name = rng.choice(_CROSS_NAMES)
        duration = rng.choice((45, 55, 60)) * 60
        pace = None
        avg_hr = rng.randint(118, 132)
        methods = ["continuous"]
        targets = ["other"]
        zone_shares = (0.35, 0.45, 0.15, 0.05)
        distance_m = 0.0
        vo2max = None
        sport = "ride"
    elif kind == "long":
        name = rng.choice(_LONG_NAMES)
        duration = _long_duration(phase, recovery_week, rng)
        pace = rng.uniform(325, 345) - 6 * progress
        avg_hr = rng.randint(137, 146) - 2 * progress
        methods = ["long_run"]
        targets = ["marathon"] if phase == "peak" else ["base"]
        zone_shares = (0.2, 0.8, 0.0, 0.0)
        distance_m = duration / pace * 1000
        vo2max = vo2max_value
        if "Trail" in name and rng.random() < 0.5:
            sport = "trail_run"
    elif kind == "quality":
        name, reps, rep_s, rep_pace, rep_hr, recovery_s, method, target = (
            _choose_quality(rng, phase, recovery_week)
        )
        warmup_s = rng.choice((720, 900))
        cooldown_s = rng.choice((480, 600))
        group = f"{activity_id}-work"
        warmup = _interval("WARMUP", warmup_s, rng.uniform(340, 365), 130, group)
        work = [
            _interval(
                "WORK",
                rep_s,
                rep_pace + rng.uniform(-4, 4) - 10 * progress,
                rep_hr - 6 * progress,
                group,
            )
            for _ in range(reps)
        ]
        recoveries = [
            _interval("RECOVERY", recovery_s, rng.uniform(350, 380), 132, group)
            for _ in range(reps - 1)
        ]
        cooldown = _interval("COOLDOWN", cooldown_s, rng.uniform(340, 365), 128, group)
        intervals = [warmup]

        for rep in range(reps):
            intervals.append(work[rep])
            if rep < reps - 1:
                intervals.append(recoveries[rep])

        intervals.append(cooldown)
        duration = sum(item.duration_s for item in intervals)
        distance_m = sum(item.distance_m for item in intervals)
        pace = duration / distance_m * 1000
        avg_hr = rep_hr - 4 - 6 * progress
        methods = [method]
        targets = [target]
        zone_shares = (0.18, 0.22, 0.35, 0.25)
        vo2max = vo2max_value
    elif kind == "recovery":
        name = "Recovery jog"
        duration = rng.randint(30, 45) * 60
        pace = rng.uniform(365, 390) - 4 * progress
        avg_hr = rng.randint(112, 124) - 2 * progress
        methods = ["continuous"]
        targets = ["recovery"]
        zone_shares = (0.45, 0.55, 0.0, 0.0)
        distance_m = duration / pace * 1000
        vo2max = vo2max_value
    else:
        name = rng.choice(_EASY_NAMES)
        duration = rng.randint(38, 58) * 60
        pace = rng.uniform(330, 360) - 8 * progress
        avg_hr = rng.randint(128, 140) - 2 * progress
        methods = ["continuous", "strides"] if "strides" in name else ["continuous"]
        targets = ["base"]
        zone_shares = (0.35, 0.65, 0.0, 0.0)
        distance_m = duration / pace * 1000
        vo2max = vo2max_value

    load = _training_load(kind, duration, phase)
    rpe = _rpe(kind, rng)
    feel = _feel(rng)
    intensity = load / max(duration / 60, 1) / 100

    started = datetime.combine(
        day,
        _start_time(kind),
        tzinfo=timezone(timedelta(minutes=60)),
    ).astimezone(timezone.utc)
    equipment_id = _shoe_for(day, sport, shoe_periods)

    description = _description(kind, phase, rng)
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
            "training_load": round(load, 1),
            "rpe": rpe,
            "feel": feel,
            "intensity": round(min(max(intensity, 0.45), 0.95), 2),
            "vo2max_garmin": round(vo2max, 1) if vo2max else None,
        },
        "methods": methods,
        "targets": targets,
        "intervals": intervals,
        "zone_times": _zone_times(duration, zone_shares),
        "equipment_id": equipment_id,
        "kind": kind,
        "load": load,
    }


def _choose_quality(rng, phase: str, recovery_week: bool):
    if recovery_week:
        return _QUALITY_SESSIONS[0]

    if phase == "base":
        return rng.choice(_QUALITY_SESSIONS[:2] + _QUALITY_SESSIONS[3:4])
    if phase == "build":
        return rng.choice(_QUALITY_SESSIONS[1:5])
    if phase == "peak":
        return rng.choice(_QUALITY_SESSIONS[2:5])
    return rng.choice(_QUALITY_SESSIONS[:3])


def _long_duration(phase: str, recovery_week: bool, rng) -> float:
    base = {
        "base": rng.randint(70, 85),
        "build": rng.randint(85, 110),
        "peak": rng.randint(95, 120),
        "taper": rng.randint(65, 80),
    }[phase]

    if recovery_week:
        base = int(base * 0.75)

    return base * 60.0


def _training_load(kind: str, duration_s: float, phase: str) -> float:
    factor = {
        "easy": 0.72,
        "recovery": 0.55,
        "long": 0.86,
        "quality": 1.05,
        "cross": 0.62,
    }[kind]

    if phase == "peak" and kind == "quality":
        factor += 0.08

    return duration_s / 60 * factor


def _rpe(kind: str, rng) -> float:
    if kind == "quality":
        return float(rng.choice((6, 7, 7, 8)))
    if kind == "long":
        return float(rng.choice((5, 6, 6, 7)))
    if kind == "recovery":
        return float(rng.choice((1, 2, 2)))
    return float(rng.choice((2, 3, 3, 4)))


def _feel(rng) -> int:
    return rng.choice((1, 2, 2, 3, 3, 3, 4, 4, 5))


def _start_time(kind: str):
    if kind in ("long", "cross"):
        return datetime.strptime("09:30", "%H:%M").time()
    return datetime.strptime("16:45", "%H:%M").time()


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


def _description(kind: str, phase: str, rng) -> str:
    if kind == "quality":
        return (
            "Quality session in the invented plan.\n"
            f"Block: {phase}. Reps on the road, recoveries easy."
        )
    if kind == "long":
        return (
            "Steady long run.\n"
            "Fuel every 40 minutes; keep the last third controlled."
        )
    if kind == "cross":
        return "Easy cross-training spin, no pace target."
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
) -> str:
    if sport == "trail_run":
        return "demo-shoe-4"

    for start, end, equipment_id in periods:
        if start <= day < end:
            return equipment_id

    return periods[-1][2]


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

    if activity["intervals"]:
        writer.replace_activity_intervals(
            activity["id"],
            activity["intervals"],
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
            "Spring 10k",
            10000.0,
            42 * 60,
            72.0,
        ),
        today + timedelta(weeks=12): (
            "City Half Marathon",
            21097.5,
            92 * 60,
            95.0,
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

    return len(shoes)


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
