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
└── tempo
non-quality
├── easy
└── recovery
unknown

Rules
-----
- quality: RPE >= 4. If RPE is missing, infer from intensity
  (IF >= 0.85 or >= 25% of time in Z3+); if that is impossible -> unknown.
- A session > 90 min is a longrun even with RPE < 4, unless its content
  (race/subt/lt1/tempo) says otherwise.
- recovery: RPE = 1 and shorter than 40 min.
- Sub-type keywords come from name/description, which usually encodes the
  planned session. Execution (RPE/duration) decides *whether* it was quality.
"""

from dataclasses import dataclass

from .model import Activity, Interval

# --- thresholds -----------------------------------------------------------

QUALITY_RPE = 4
LONGRUN_S = 90 * 60

INTENSITY_QUALITY = 0.85      # IF at/above this implies quality
QUALITY_ZONE_SHARE = 0.25     # share of time in Z3+

RECOVERY_RPE = 1
RECOVERY_MAX_DURATION_S = 40 * 60

TEMPO_BLOCK_S = 10 * 60

SHORT_MAX_S = 240
MEDIUM_MAX_S = 350

# --- keywords -------------------------------------------------------------

RACE_WORDS = ("race", "wettkampf")
SUBT_WORDS = ("subt",)
LT1_WORDS = ("lt1", "lt 1")
TEMPO_WORDS = ("tempo", "threshold", "schwelle")


@dataclass(frozen=True)
class Category:

    group: str                  # "quality" | "non-quality" | "unknown"
    kind: str                   # "intervals" | "longrun" | "race" | "tempo" | "easy" | "recovery" | "unknown"
    detail: str | None = None   # "subt-short" | "subt-medium" | "subt-long" | "lt1" | "other"

    @property
    def path(self) -> str:
        parts = [self.group, self.kind]
        if self.detail:
            parts.append(self.detail)
        return "/".join(parts)

    @property
    def quality(self) -> bool:
        return self.group == "quality"


UNKNOWN = Category("unknown", "unknown")


def classify(
    activity: Activity,
    intervals: list[Interval] | None = None,
) -> Category:
    """Classify one activity, optionally using its interval structure."""
    intervals = intervals or []
    text = f"{activity.name} {activity.description}".lower()
    work = [
        i for i in intervals
        if i.type == "WORK" and i.duration_s > 0
    ]

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

    subt = _subt_detail(text, work)
    if subt is not None:
        return Category("quality", "intervals", subt)

    if _has(text, LT1_WORDS):
        return Category("quality", "intervals", "lt1")

    if _has(text, TEMPO_WORDS) or _has_sustained_block(work):
        return Category("quality", "tempo")

    if activity.duration_s > LONGRUN_S:
        return Category("quality", "longrun")

    return Category("quality", "intervals", "other")


def _subt_detail(text: str, work: list[Interval]) -> str | None:
    if not _has(text, SUBT_WORDS):
        return None

    if not work:
        return "subt"

    avg_rep = sum(i.duration_s for i in work) / len(work)

    if avg_rep <= SHORT_MAX_S:
        return "subt-short"
    if avg_rep <= MEDIUM_MAX_S:
        return "subt-medium"
    return "subt-long"


def _has_sustained_block(work: list[Interval]) -> bool:
    return any(i.duration_s >= TEMPO_BLOCK_S for i in work)


# --- non-quality ----------------------------------------------------------

def _is_recovery(activity: Activity) -> bool:
    return (
        activity.rpe == RECOVERY_RPE
        and activity.duration_s < RECOVERY_MAX_DURATION_S
    )


# --- helpers --------------------------------------------------------------

def _has(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)
