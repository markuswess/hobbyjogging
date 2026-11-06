"""Canonical sport vocabulary shared by importers, reports, and manual entry.

One vocabulary, one alias table. Sources name sports differently (FIT
``running``/``cycling``, Intervals ``TrailRun``/``GravelRide``), so every
importer normalizes through :func:`canonical_sport` before writing. Reports
and quality rules branch on the canonical names and the sport groups defined
here.
"""

from __future__ import annotations

UNKNOWN_SPORTS = frozenset({"", "generic", "other", "unknown"})

RUN_SPORTS = frozenset(
    {"run", "trail_run", "treadmill_run", "track_run", "virtual_run"}
)
RIDE_SPORTS = frozenset(
    {"ride", "gravel_ride", "mtb_ride", "virtual_ride"}
)
PACE_SPORTS = RUN_SPORTS | RIDE_SPORTS
WALK_SPORTS = frozenset({"walk", "hike"})
WATER_SPORTS = frozenset({"swim", "row", "kayaking", "sup", "surfing"})
SNOW_SPORTS = frozenset(
    {"alpine_skiing", "cross_country_skiing", "snowboarding"}
)
STRENGTH_SPORTS = frozenset({"training"})

CANONICAL_SPORTS = frozenset(
    RUN_SPORTS
    | RIDE_SPORTS
    | WALK_SPORTS
    | WATER_SPORTS
    | SNOW_SPORTS
    | STRENGTH_SPORTS
    | {"soccer", "racket", "other"}
)

# Sports where distance is not recorded or not meaningful. The canonical
# distance is forced to zero for these; a manual distance may still override.
# "workout" is an Intervals type rather than a canonical sport, but it reaches
# the database for generic Football/Badminton activities and must not keep
# GPS drift.
NO_DISTANCE_SPORTS = frozenset(
    {
        "treadmill_run",
        "virtual_run",
        "soccer",
        "racket",
        "training",
        "other",
        "workout",
    }
)

SPORT_LABELS = {
    "run": "Run",
    "trail_run": "Trail Run",
    "treadmill_run": "Treadmill Run",
    "track_run": "Track Run",
    "virtual_run": "Virtual Run",
    "ride": "Ride",
    "gravel_ride": "Gravel Ride",
    "mtb_ride": "MTB Ride",
    "virtual_ride": "Virtual Ride",
    "swim": "Swim",
    "walk": "Walk",
    "hike": "Hike",
    "row": "Row",
    "kayaking": "Kayaking",
    "sup": "SUP",
    "surfing": "Surfing",
    "alpine_skiing": "Alpine Skiing",
    "cross_country_skiing": "Cross-Country Skiing",
    "snowboarding": "Snowboarding",
    "soccer": "Soccer",
    "racket": "Racket Sport",
    "training": "Strength Training",
    "other": "Other",
}

# Keys are normalized tokens: lowercase, spaces and hyphens become underscores.
SPORT_ALIASES = {
    # FIT sport names
    "running": "run",
    "trail_running": "trail_run",
    "cycling": "ride",
    "walking": "walk",
    "hiking": "hike",
    "swimming": "swim",
    "rowing": "row",
    "stand_up_paddleboarding": "sup",
    "cross_country_skiing": "cross_country_skiing",
    "alpine_skiing": "alpine_skiing",
    "kayaking": "kayaking",
    "racket": "racket",
    "training": "training",
    "surfing": "surfing",
    "generic": "other",
    # Intervals.icu type names
    "run": "run",
    "ride": "ride",
    "trailrun": "trail_run",
    "treadmillrun": "treadmill_run",
    "trackrun": "track_run",
    "virtualrun": "virtual_run",
    "gravelride": "gravel_ride",
    "mountainbikeride": "mtb_ride",
    "virtualride": "virtual_ride",
    "ebikeride": "ride",
    "alpineski": "alpine_skiing",
    "crosscountryskiing": "cross_country_skiing",
    "snowboarding": "snowboarding",
    "soccer": "soccer",
    "football": "soccer",
    "padel": "racket",
    "tennis": "racket",
    "squash": "racket",
    "badminton": "racket",
    "strengthtraining": "training",
    "weighttraining": "training",
    "other": "other",
    "unknown": "other",
}

# FIT records both a sport and a sub-sport; the pair carries the specificity
# (a gravel ride is a ride with sub-sport gravel_cycling).
SUB_SPORT_ALIASES = {
    ("cycling", "gravel_cycling"): "gravel_ride",
    ("cycling", "mountain"): "mtb_ride",
    ("cycling", "road"): "ride",
    ("cycling", "generic"): "ride",
    ("cycling", "virtual_activity"): "virtual_ride",
    ("cycling", "indoor_cycling"): "virtual_ride",
    ("cycling", "cyclocross"): "ride",
    ("cycling", "bmx"): "ride",
    ("cycling", "e_biking"): "ride",
    ("cycling", "track_cycling"): "ride",
    ("running", "trail"): "trail_run",
    ("running", "trail_running"): "trail_run",
    ("running", "treadmill"): "treadmill_run",
    ("running", "track"): "track_run",
    ("running", "virtual_activity"): "virtual_run",
    ("running", "generic"): "run",
    ("swimming", "lap_swimming"): "swim",
    ("swimming", "open_water"): "swim",
    ("training", "strength_training"): "training",
    ("alpine_skiing", "backcountry"): "alpine_skiing",
    ("cross_country_skiing", "skate_skiing"): "cross_country_skiing",
    ("cross_country_skiing", "classic_skiing"): "cross_country_skiing",
}


def normalize_token(value: object) -> str:
    """Normalize a raw sport token: lowercase, spaces/hyphens to underscores."""
    text = str(value or "").strip().lower()
    return text.replace(" ", "_").replace("-", "_")


def canonical_sport(sport: object, sub_sport: object = None) -> str:
    """Map a source's sport/sub-sport pair to the canonical sport name.

    Unrecognized tokens pass through normalized, so a new source sport is
    preserved rather than silently relabeled.
    """
    raw = normalize_token(sport)
    sub = normalize_token(sub_sport)

    if (raw, sub) in SUB_SPORT_ALIASES:
        return SUB_SPORT_ALIASES[(raw, sub)]

    if raw in SPORT_ALIASES:
        return SPORT_ALIASES[raw]

    if raw in UNKNOWN_SPORTS and sub in SPORT_ALIASES:
        return SPORT_ALIASES[sub]

    return raw


def is_known_sport(value: object) -> bool:
    """True when a sport value is specific (not a placeholder/unknown)."""
    token = normalize_token(value)
    return bool(token) and token not in UNKNOWN_SPORTS
