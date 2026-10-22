"""Workout categorization.

Categories
----------
quality
├── intervals
│   ├── subt-short   (avg rep <= 4:00)
│   ├── subt-medium  (avg rep 4:01-5:50)
│   ├── subt-long    (avg rep > 5:50)
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
- quality: RPE >= 4. If RPE is missing, infer from intensity
  (IF >= 0.85 or >= 25% of time in Z3+); if that is impossible -> unknown.
- A session > 90 min is a longrun even with RPE < 4, unless its content
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
"""

from dataclasses import dataclass

from .analysis import RUN_TYPES, classify_interval
from .model import Activity, Interval

# --- thresholds -----------------------------------------------------------

QUALITY_RPE = 4
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
SUBT_WORDS = ("subt",)
LT1_WORDS = ("lt1", "lt 1")
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

GROUP_ORDER = {
    "quality": 0,
    "non-quality": 1,
    "cross-training": 2,
    "unknown": 3,
}


@dataclass
class CategoryStat:
    """Aggregated training volume for one category."""

    category: Category
    sessions: int = 0
    time_s: float = 0
    load: float = 0
    time_share: float = 0
    load_share: float = 0

    @property
    def path(self) -> str:
        return self.category.path


def classify(
    activity: Activity,
    intervals: list[Interval] | None = None,
) -> Category:
    """Classify one activity, optionally using its interval structure."""
    if activity.type not in RUN_TYPES:
        return CROSS_TRAINING

    intervals = intervals or []
    text = activity.name.lower()
    work = [
        i for i in intervals
        if i.type == "WORK" and i.duration_s > 0
    ]

    support = _race_support(text)
    if support is not None:
        return Category("quality", "race-support", support)

    quality = _is_quality(activity)

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

def _is_quality(activity: Activity) -> bool | None:
    """Quality decision from RPE, falling back to intensity signals."""
    if activity.rpe is not None:
        return activity.rpe >= QUALITY_RPE

    if activity.intensity is not None:
        return activity.intensity >= INTENSITY_QUALITY

    zones = activity.pace_zone_times or activity.hr_zone_times
    total = sum(zones)

    if total > 0:
        return sum(zones[2:]) / total >= QUALITY_ZONE_SHARE

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

    return Category("quality", "intervals", "other")


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


# --- aggregation ----------------------------------------------------------

def category_breakdown(
    activities: list[Activity],
    intervals_by_id: dict[str, list[Interval]] | None = None,
) -> list[CategoryStat]:
    """Aggregate activities by category, grouped and sorted by time.

    ``intervals_by_id`` is optional; when provided it refines subT rep
    lengths. Without it, subT sessions collapse into ``intervals/subt``.
    """
    intervals_by_id = intervals_by_id or {}
    stats: dict[str, CategoryStat] = {}

    for activity in activities:
        category = classify(activity, intervals_by_id.get(activity.id))
        stat = stats.get(category.path)

        if stat is None:
            stat = stats[category.path] = CategoryStat(category)

        stat.sessions += 1
        stat.time_s += activity.duration_s or 0
        stat.load += activity.training_load or 0

    total_time = sum(stat.time_s for stat in stats.values())
    total_load = sum(stat.load for stat in stats.values())

    for stat in stats.values():
        stat.time_share = stat.time_s / total_time if total_time else 0
        stat.load_share = stat.load / total_load if total_load else 0

    return sorted(
        stats.values(),
        key=lambda stat: (
            GROUP_ORDER.get(stat.category.group, len(GROUP_ORDER)),
            -stat.time_s,
        ),
    )
