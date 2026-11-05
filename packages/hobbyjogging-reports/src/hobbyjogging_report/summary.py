"""Training summaries used by period reports."""

from hobbyjogging_core.model import Activity, WellnessDay

from .analysis import RUN_TYPES
from .classify import classify


def zone_3_4_time(zone_times):
    """Return combined time spent in zones 3 and 4."""
    if not zone_times:
        return 0

    return sum(zone_times[2:4])


def summarize_training(activities: list[Activity]):
    """Aggregate running/cross-training totals and quality sessions."""
    result = {
        "run_time": 0,
        "run_distance": 0,
        "run_load": 0,

        "cross_time": 0,
        "cross_load": 0,

        "quality": [],
        "z3_z4_time": 0,
        "rpe": 0,

        "run_feel": 0,
        "run_feel_count": 0,
        "cross_feel": 0,
        "cross_feel_count": 0,
    }

    for activity in activities:
        time = activity.duration_s
        distance = activity.distance_m
        load = activity.training_load or 0
        rpe = activity.rpe or 0

        if activity.type in RUN_TYPES:
            result["run_time"] += time
            result["run_distance"] += distance
            result["run_load"] += load
            result["rpe"] += rpe

            if activity.feel is not None:
                result["run_feel"] += activity.feel
                result["run_feel_count"] += 1

            category = classify(activity)

            # Warm-ups/cool-downs are quality in the breakdown, but they
            # would clutter the per-session detail list.
            if category.quality and category.kind != "race-support":
                result["quality"].append(activity)

        if activity.type == "run":
            result["z3_z4_time"] += zone_3_4_time(
                activity.pace_zone_times
            )

        elif activity.type == "trail_run":
            result["z3_z4_time"] += zone_3_4_time(
                activity.hr_zone_times
            )

        else:
            result["cross_time"] += time
            result["cross_load"] += load

            if activity.feel is not None:
                result["cross_feel"] += activity.feel
                result["cross_feel_count"] += 1

    return result


def recovery_summary(wellness: list[WellnessDay]):
    """Average HRV, resting HR, and sleep across the given days."""

    def avg(values):
        return (
            round(sum(values) / len(values), 1)
            if values
            else None
        )

    hrv = []
    rhr = []
    sleep = []

    for day in wellness:
        if day.hrv:
            hrv.append(day.hrv)

        if day.resting_hr:
            rhr.append(day.resting_hr)

        if day.sleep_s:
            sleep.append(day.sleep_s)

    return {
        "hrv": avg(hrv),
        "rhr": avg(rhr),
        "sleep": avg(sleep),
    }
