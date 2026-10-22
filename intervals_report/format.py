from .classify import classify
from .sources.intervals_api import to_activity


def fmt_time(seconds):

    if not seconds:
        return "-"

    seconds = int(seconds)

    minutes = seconds // 60

    h = minutes // 60
    m = minutes % 60

    if h:
        return f"{h}h{m:02d}"

    return f"{m}min"

def fmt_zones(zone_times):

    if not zone_times:
        return "-"

    return " | ".join(
        f"Z{i+1} {fmt_time(t)}"
        for i, t in enumerate(zone_times)
        if t
    )


def pace(activity):

    try:

        sec = (
            activity["moving_time"]
            /
            activity["distance"]
            *
            1000
        )

        return (
            f"{int(sec//60)}:"
            f"{int(sec%60):02d}/km"
        )

    except Exception:
        return "-"

def format_subt_result(result):

    duration = result["duration"] / result["count"]

    mins = int(duration // 60)
    secs = round(duration % 60)

    if secs == 60:
        mins += 1
        secs = 0

    interval_duration = f"{mins}:{secs:02d}"

    return (
        f'{result["count"]}x{interval_duration} '
        f'subT-{result["category"]}: '
        f'{format_pace(result["pace"])}/km, '
        f'{result["hr"]} bpm'
    )

def last_four_nights(wellness):

    wellness = sorted(
        wellness,
        key=lambda x: x.get("id", ""),
        reverse=True,
    )

    return wellness[:4]

def zone_3_4_time(zone_times):
    """Return combined time spent in zones 3 and 4."""
    if not zone_times:
        return 0

    return sum(zone_times[2:4])

def summarize_training(activities):

    run_types = {
        "Run",
        "TrailRun",
    }

    result = {
        "run_time": 0,
        "run_distance": 0,
        "run_load": 0,

        "cross_time": 0,
        "cross_load": 0,

        "quality": [],
        "z3_z4_time": 0,
        "rpe": 0,
    }


    for a in activities:

        sport = a.get("type","")

        time = a.get(
            "moving_time",
            0
        )

        distance = a.get(
            "distance",
            0
        )

        load = (
            a.get("icu_training_load")
            or 0
        )

        rpe = (
            a.get("icu_rpe")
            or 0
        )


        if sport in run_types:
            result["run_time"] += time
            result["run_distance"] += distance
            result["run_load"] += load
            result["rpe"] += rpe 


            if classify(to_activity(a)).quality:
                result["quality"].append(a)

        if sport == "Run":
            result["z3_z4_time"] += zone_3_4_time(
                a.get("pace_zone_times")
            )

        elif sport == "TrailRun":

            result["z3_z4_time"] += zone_3_4_time(
                a.get("icu_hr_zone_times")
            )

        else:

            result["cross_time"] += time
            result["cross_load"] += load


    return result



def recovery_summary(wellness):

    def avg(values):

        return (
            round(sum(values)/len(values),1)
            if values
            else None
        )


    hrv = []
    rhr = []
    sleep = []


    for w in wellness:

        if w.get("hrv"):
            hrv.append(w["hrv"])

        if w.get("restingHR"):
            rhr.append(w["restingHR"])

        if w.get("sleepSecs"):
            sleep.append(w["sleepSecs"])


    return {
        "hrv": avg(hrv),
        "rhr": avg(rhr),
        "sleep": avg(sleep),
    }

def latest_recovery(wellness):

    if not wellness:
        return {
            "hrv": None,
            "rhr": None,
            "sleep": None,
        }

    # newest entry
    w = sorted(
        wellness,
        key=lambda x: x.get("id", ""),
        reverse=True
    )[0]

    return {
        "hrv": w.get("hrv"),
        "rhr": w.get("restingHR"),
        "sleep": w.get("sleepSecs"),
    }
def pace_from_speed(speed):
    """Return pace as seconds/km."""
    if not speed or speed <= 0:
        return None
    return 1000 / speed


def format_pace(seconds):
    """Format seconds/km as M:SS."""
    if seconds is None:
        return "-"
    seconds = round(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def classify_subt(duration):
    """Classify subT interval length."""
    if duration <= 240:
        return "short"
    elif duration <= 350:
        return "medium"
    else:
        return "long"


def extract_subt_intervals(intervals):
    """
    Extract WORK blocks from an Intervals.icu icu_intervals list.

    Returns one entry per group_id.
    """

    work = [
        i for i in intervals
        if i.get("type") == "WORK"
        and i.get("moving_time")
        and i.get("distance")
    ]

    groups = {}

    for interval in work:
        group_id = interval.get("group_id")

        # If there is no group_id, keep it as its own group.
        if not group_id:
            group_id = f"interval-{interval['id']}"

        groups.setdefault(group_id, []).append(interval)

    results = []

    for group_id, group in groups.items():

        # Sort chronologically
        group.sort(key=lambda x: x["start_time"])

        total_time = sum(
            i["moving_time"] for i in group
        )

        total_distance = sum(
            i["distance"] for i in group
        )

        if total_time <= 0 or total_distance <= 0:
            continue

        avg_speed = total_distance / total_time
        avg_pace = pace_from_speed(avg_speed)

        # Time-weighted HR
        hr_values = [
            (i["average_heartrate"], i["moving_time"])
            for i in group
            if i.get("average_heartrate") is not None
        ]

        if hr_values:
            avg_hr = (
                sum(hr * t for hr, t in hr_values)
                / sum(t for _, t in hr_values)
            )
            avg_hr = round(avg_hr)
        else:
            avg_hr = None

        results.append({
            "group_id": group_id,
            "count": len(group),
            "duration": total_time,
            "distance": total_distance,
            "pace": avg_pace,
            "hr": avg_hr,
            "category": classify_subt(total_time / len(group)),
        })

    return results

def subt_summary_for_activity(activity, intervals):
    """Return subT report lines for an activity, given its intervals."""

    name = (activity.get("name") or "").lower()
    description = (activity.get("description") or "").lower()

    # Only inspect activities that look like subT workouts.
    if "subt" not in name and "subt" not in description:
        return None

    results = extract_subt_intervals(intervals)

    if not results:
        return None

    return [
        format_subt_result(result)
        for result in results
    ]


def get_subt_summary(api, activity):
    """Return compact subT interval summary for an activity."""

    name = (activity.get("name") or "").lower()
    description = (activity.get("description") or "").lower()

    # Only inspect activities that look like subT workouts.
    if "subt" not in name and "subt" not in description:
        return None

    try:
        intervals = api.get_activity_intervals(activity["id"])
    except Exception:
        return None

    return subt_summary_for_activity(activity, intervals)

def format_activity(api, a, heading):

    lines = [
        f"\n### {heading}",
        f"- Duration: {fmt_time(a.get('moving_time'))}",
    ]

    if a.get("distance"):
        lines.append(f"- Distance: {a['distance']/1000:.1f} km")

    if a.get("type") in ("Run", "TrailRun"):
        lines.append(f"- Pace: {pace(a)}")

    if a.get("average_heartrate"):
        lines.append(f"- HR: {a['average_heartrate']:.0f} avg")

    if a.get("icu_training_load"):
        lines.append(f"- Load: {a['icu_training_load']:.0f}")

    if a.get("icu_rpe"):
        lines.append(f"- RPE: {a['icu_rpe']:.0f}")

    if a.get("pace_zone_times"):
        lines.append(f"- Pace zones: {fmt_zones(a['pace_zone_times'])}")

    if a.get("description"):
        lines.append(f"- Description: {a['description']}")

    subt = get_subt_summary(api, a)

    if subt:
        lines.append("\n### subT report")
        for line in subt:
            lines.append(f"- {line}")

    return lines
