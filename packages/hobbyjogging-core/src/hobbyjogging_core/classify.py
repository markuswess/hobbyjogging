"""Workout categorization (the heuristic).

Categories
----------
quality
├── intervals
│   ├── subt-short   (avg rep <= 4:00)
│   ├── subt-medium  (avg rep 4:01-7:00)
│   ├── subt-long    (avg rep > 7:00)
│   ├── lt1
│   └── other
├── longrun          (> 90 min)
├── race
├── race-support     (warmup / cooldown)
└── tempo
non-quality
├── easy
└── recovery
cross-training
unknown

Rules
-----
- quality: RPE > 3. RPE exactly 3 can also be quality when the session
  has explicit quality content (race/subT/LT1/tempo) or intensity/zones
  indicate quality. If RPE is missing, infer from intensity
  (IF >= 0.85 or >= 25% of time in Z3+); if impossible -> unknown.
- A session > 90 min is a longrun even with low RPE, unless its content
  (race/subt/lt1/tempo) says otherwise.
- recovery: RPE = 1 and shorter than 40 min.
- Sub-type keywords come from the activity name only. Descriptions often
  mention alternatives ("did 3x10@LT1 instead of subT") and would mislead.
- LT1 wins over subT when both appear (subT was sometimes added to a name
  only to include a session in the subT report).
- Rep length ignores work intervals shorter than 60 s (strides).
- Race warm-ups and cool-downs are quality/race-support, identified by
  name; this overrides the RPE rule (they are usually RPE 1-3).
- Non-run activities are cross-training.

The heuristic lives in core because importers, maintenance and reports all
need the same decision; only the display aggregation stays in the reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from .model import Activity, Interval
from .sports import RUN_SPORTS

RUN_TYPES = RUN_SPORTS

# Rep-length buckets, shared with the subT analysis.
CATEGORY_SHORT = "short"
CATEGORY_MEDIUM = "medium"
CATEGORY_LONG = "long"
SUBT_CATEGORIES = (CATEGORY_SHORT, CATEGORY_MEDIUM, CATEGORY_LONG)

LT1_WORDS = ("lt1", "lt 1")

# Average rep duration thresholds (seconds), matching the report logic.
SHORT_MAX_S = 240
MEDIUM_MAX_S = 420

# Work interval filtering. Older Intervals.icu activities mark warm-up,
# cool-down and recovery jogs as WORK; work reps form the fast pace cluster.
WORK_MIN_DURATION_S = 60
WORK_MIN_DISTANCE_M = 100
WORK_PACE_BAND = 1.20
WORK_MIN_HR_SHARE = 0.85
WORK_SLOW_PACE_BAND = 1.10

# --- thresholds -----------------------------------------------------------

QUALITY_RPE = 3              # above this is always quality
LONGRUN_S = 90 * 60

INTENSITY_QUALITY = 0.85      # IF at/above this implies quality
QUALITY_ZONE_SHARE = 0.25     # share of time in Z3+

RECOVERY_RPE = 1
RECOVERY_MAX_DURATION_S = 40 * 60

TEMPO_BLOCK_S = 10 * 60
SUBT_MIN_REP_S = 60           # ignore strides when measuring subT reps

# --- keywords -------------------------------------------------------------

RACE_WORDS = ("race", "wettkampf")
WARMUP_WORDS = ("warm up", "warm-up", "warmup")
COOLDOWN_WORDS = ("cool down", "cool-down", "cooldown")
SUBT_WORDS = ("subt", "subthreshold", "sub-threshold")
TEMPO_WORDS = ("tempo", "threshold", "schwelle")


@dataclass(frozen=True)
class Category:

    group: str                  # "quality" | "non-quality" | "cross-training" | "unknown"
    kind: str = ""              # "intervals" | "longrun" | "race" | "race-support" | "tempo" | "easy" | "recovery"
    detail: str | None = None   # "subt-short" | "subt-medium" | "subt-long" | "lt1" | "other"

    @property
    def path(self) -> str:
        parts = (self.group, self.kind, self.detail)
        return "/".join(part for part in parts if part)

    @property
    def quality(self) -> bool:
        return self.group == "quality"


UNKNOWN = Category("unknown")
CROSS_TRAINING = Category("cross-training")


def classify_interval(duration_s: float) -> str:
    """Classify an interval by its (average rep) duration."""
    if duration_s <= SHORT_MAX_S:
        return CATEGORY_SHORT
    if duration_s <= MEDIUM_MAX_S:
        return CATEGORY_MEDIUM
    return CATEGORY_LONG


def work_intervals(intervals: list[Interval]) -> list[Interval]:
    """Return the intervals that are actual work reps.

    Older Intervals.icu data labels warm-up, cool-down and recovery jogs as
    WORK as well. Work reps are the fast pace cluster; everything else is
    slower. Strides and GPS artifacts are ignored. When there is not enough
    pace data to separate the clusters, all WORK intervals are returned.
    """
    work = [
        i for i in intervals
        if i.type == "WORK" and i.duration_s > 0
    ]

    paced = [
        i for i in work
        if i.duration_s >= WORK_MIN_DURATION_S
        and i.distance_m >= WORK_MIN_DISTANCE_M
    ]

    if len(paced) < 3:
        return work

    def pace(i: Interval) -> float:
        return i.duration_s / i.distance_m * 1000

    ordered = sorted(paced, key=pace)

    # Use the fastest third as the reference so a single flier cannot pull
    # the band down, while recovery jogs cannot pull it up.
    fastest = ordered[:max(1, len(ordered) // 3)]
    reference = median(pace(i) for i in fastest)

    reps = [
        i for i in paced
        if pace(i) <= reference * WORK_PACE_BAND
    ]

    if not reps:
        return work

    # Warm-ups can sit just inside the pace band, but their heart rate is
    # still clearly below the work reps. Only drop slow, low-HR intervals so
    # short reps with heart-rate lag are kept.
    hrs = [i.avg_hr for i in reps if i.avg_hr is not None]

    if not hrs:
        return reps

    median_pace = median(pace(i) for i in reps)
    min_hr = max(hrs) * WORK_MIN_HR_SHARE

    filtered = [
        i for i in reps
        if not (
            i.avg_hr is not None
            and i.avg_hr < min_hr
            and pace(i) > median_pace * WORK_SLOW_PACE_BAND
        )
    ]

    return filtered or reps


def classify(
    activity: Activity,
    intervals: list[Interval] | None = None,
    *,
    use_stored: bool = True,
) -> Category:
    """Classify one activity, optionally using its interval structure.

    With ``use_stored`` (the default for reports) a stored workout
    classification wins: its quality flag decides quality vs non-quality and
    its methods refine the category when the name says nothing. Activities
    without a stored classification fall back to the heuristic below.

    ``use_stored=False`` is the pure heuristic. The workout-classification
    backfill must use it, otherwise it would read back its own output.
    """
    if activity.type not in RUN_TYPES:
        return CROSS_TRAINING

    intervals = intervals or []
    text = activity.name.lower()
    work = work_intervals(intervals)

    support = _race_support(text)
    if support is not None:
        return Category("quality", "race-support", support)

    stored = activity.quality if use_stored else None

    if stored is not None:
        if stored:
            return _quality_category(activity, text, work)

        if "recovery" in activity.workout_targets or _is_recovery(activity):
            return Category("non-quality", "recovery")

        return Category("non-quality", "easy")

    quality = _is_quality(activity, text, work)

    if quality is True:
        return _quality_category(activity, text, work)

    # Duration wins over non-quality: a long run stays a longrun.
    if activity.duration_s > LONGRUN_S:
        return Category("quality", "longrun")

    if quality is None:
        return UNKNOWN

    if _is_recovery(activity):
        return Category("non-quality", "recovery")

    return Category("non-quality", "easy")


# --- quality --------------------------------------------------------------

def _is_quality(
    activity: Activity,
    text: str,
    work: list[Interval],
) -> bool | None:
    """Quality decision from RPE, falling back to intensity signals."""
    if activity.rpe is None:
        return _intensity_quality(activity)

    if activity.rpe > QUALITY_RPE:
        return True

    if activity.rpe == QUALITY_RPE:
        return _maybe_quality(activity, text, work)

    return False


def _maybe_quality(
    activity: Activity,
    text: str,
    work: list[Interval],
) -> bool:
    """RPE 3 sessions are quality only when something else backs it up."""
    if _has_quality_content(text, work):
        return True

    return _intensity_quality(activity) is True


def _has_quality_content(text: str, work: list[Interval]) -> bool:
    return (
        _has(text, RACE_WORDS)
        or _has(text, LT1_WORDS)
        or _has(text, SUBT_WORDS)
        or _has(text, TEMPO_WORDS)
        or _has_sustained_block(work)
    )


def _intensity_quality(activity: Activity) -> bool | None:
    if (
        activity.intensity is not None
        and activity.intensity >= INTENSITY_QUALITY
    ):
        return True

    zones = activity.pace_zone_times or activity.hr_zone_times
    total = sum(zones)

    if total > 0:
        return sum(zones[2:]) / total >= QUALITY_ZONE_SHARE

    if activity.intensity is not None:
        return False

    return None


def _quality_category(
    activity: Activity,
    text: str,
    work: list[Interval],
) -> Category:
    # Content wins over duration: explicit types first, longrun last.
    if _has(text, RACE_WORDS):
        return Category("quality", "race")

    if _has(text, LT1_WORDS):
        return Category("quality", "intervals", "lt1")

    subt = _subt_detail(text, work)
    if subt is not None:
        return Category("quality", "intervals", subt)

    if _has(text, TEMPO_WORDS) or _has_sustained_block(work):
        return Category("quality", "tempo")

    if activity.duration_s > LONGRUN_S:
        return Category("quality", "longrun")

    # A stored method is more specific than an uninformative name.
    stored = _stored_quality_category(activity)
    if stored is not None:
        return stored

    return Category("quality", "intervals", "other")


def _stored_quality_category(activity: Activity) -> Category | None:
    """Category from stored workout methods, when the name says nothing."""
    methods = set(activity.workout_methods)

    if "long_run" in methods:
        return Category("quality", "longrun")
    if "race" in methods:
        return Category("quality", "race")
    if "intervals" in methods or "progression" in methods:
        return Category("quality", "intervals", "other")

    return None


def _subt_detail(text: str, work: list[Interval]) -> str | None:
    if not _has(text, SUBT_WORDS):
        return None

    reps = [i.duration_s for i in work if i.duration_s >= SUBT_MIN_REP_S]
    if not reps:
        return "subt"

    return f"subt-{classify_interval(sum(reps) / len(reps))}"


def _has_sustained_block(work: list[Interval]) -> bool:
    return any(i.duration_s >= TEMPO_BLOCK_S for i in work)


def _race_support(text: str) -> str | None:
    """Warmup/cooldown label, matched by name before the RPE rule."""
    if _has(text, WARMUP_WORDS):
        return "warmup"
    if _has(text, COOLDOWN_WORDS):
        return "cooldown"
    return None


# --- non-quality ----------------------------------------------------------

def _is_recovery(activity: Activity) -> bool:
    return (
        activity.rpe == RECOVERY_RPE
        and activity.duration_s < RECOVERY_MAX_DURATION_S
    )


# --- helpers --------------------------------------------------------------

def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)
