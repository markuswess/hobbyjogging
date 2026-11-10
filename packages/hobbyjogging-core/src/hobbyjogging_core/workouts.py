"""Canonical workout method/target vocabulary and quality rules.

A session can carry several methods and several targets (e.g. a long run with
a marathon-pace finish is ``long_run`` with targets ``base`` + ``marathon``).
The database stores them as sets; this module defines the tokens, labels,
aliases, and the quality rule shared by importers and reports.
"""

from __future__ import annotations

WORKOUT_METHODS = {
    "continuous": "Continuous",
    "intervals": "Intervals",
    "long_run": "Long Run",
    "progression": "Progression",
    "race": "Race",
    "strides": "Strides",
    "other": "Other",
}

WORKOUT_TARGETS = {
    "base": "Base",
    "lt1": "LT1",
    "subthreshold": "Sub-Threshold",
    "threshold": "Threshold",
    "vo2max": "VO2max",
    "speed": "Speed",
    "marathon": "Marathon",
    "recovery": "Recovery",
    "other": "Other",
}

# A session is quality if any method or target below is present. Strides alone
# never make a session quality; base/recovery targets do not either.
QUALITY_METHODS = frozenset(
    {"intervals", "long_run", "progression", "race"}
)
QUALITY_TARGETS = frozenset(
    {"lt1", "subthreshold", "threshold", "vo2max", "speed", "marathon"}
)

METHOD_ALIASES = {
    "easy": "continuous",
    "steady": "continuous",
    "recovery": "continuous",
    "reps": "intervals",
    "repetitions": "intervals",
    "interval": "intervals",
    # "tempo" is retired: a tempo run is continuous with a threshold target.
    "tempo": "continuous",
    "tempo_run": "continuous",
    "long": "long_run",
    "longrun": "long_run",
    "progressive": "progression",
    "progression_run": "progression",
    "competition": "race",
    "stride": "strides",
    "unknown": "other",
}

TARGET_ALIASES = {
    "easy": "base",
    "aerobic": "base",
    "aerobic_threshold": "lt1",
    "subt": "subthreshold",
    "sub_threshold": "subthreshold",
    "lactate_threshold": "threshold",
    "vo2": "vo2max",
    "speedwork": "speed",
    "neuromuscular": "speed",
    "marathon_specific": "marathon",
    "regeneration": "recovery",
    "unknown": "other",
}

# Sheet ``Trainigstyp`` codes: (methods, targets, extra tags).
SHEET_TYPE_CODES = {
    "r": ({"continuous"}, {"recovery"}, set()),
    "i": ({"intervals"}, {"vo2max"}, set()),
    "bi": ({"intervals"}, {"vo2max"}, {"hills"}),
    "b": ({"continuous"}, {"base"}, set()),
    "fs": ({"intervals"}, set(), set()),
    "k": (set(), set(), {"strength"}),
    "ll": ({"long_run"}, {"base"}, set()),
    "lt": ({"race"}, {"other"}, set()),
    "tdl": ({"continuous"}, {"threshold"}, set()),
    "u": (set(), set(), {"bad data"}),
    "idl": ({"continuous"}, set(), set()),
}


def normalize_token(value: object) -> str:
    """Normalize a raw token: lowercase, spaces/hyphens to underscores."""
    text = str(value or "").strip().lower()
    return text.replace(" ", "_").replace("-", "_")


def canonical_method(value: object) -> str:
    """Return a canonical workout method token."""
    token = normalize_token(value)
    token = METHOD_ALIASES.get(token, token)
    return token if token in WORKOUT_METHODS else "other"


def canonical_target(value: object) -> str:
    """Return a canonical workout target token."""
    token = normalize_token(value)
    token = TARGET_ALIASES.get(token, token)
    return token if token in WORKOUT_TARGETS else "other"


def method_label(value: object) -> str:
    """Human label for a method token."""
    token = canonical_method(value)
    return WORKOUT_METHODS.get(token, token)


def target_label(value: object) -> str:
    """Human label for a target token."""
    token = canonical_target(value)
    return WORKOUT_TARGETS.get(token, token)


def is_quality(
    methods: object = (),
    targets: object = (),
) -> bool | None:
    """Return whether a session is quality, non-quality, or unknown.

    ``True`` when any quality method/target is present, ``False`` when there
    are values but none are quality, ``None`` when both sets are empty.
    """
    method_set = {canonical_method(value) for value in methods}
    target_set = {canonical_target(value) for value in targets}

    if method_set & QUALITY_METHODS or target_set & QUALITY_TARGETS:
        return True
    if method_set or target_set:
        return False
    return None


def classification_for_category(
    group: str,
    kind: str = "",
    detail: str | None = None,
) -> tuple[set[str], set[str]]:
    """Map the reports classifier's category to method/target sets."""
    if group == "quality":
        if kind == "intervals":
            if detail == "lt1":
                return {"intervals"}, {"lt1"}
            if detail and detail.startswith("subt"):
                return {"intervals"}, {"subthreshold"}
            return {"intervals"}, {"other"}
        if kind == "longrun":
            return {"long_run"}, {"base"}
        if kind == "race":
            return {"race"}, {"other"}
        if kind == "race-support":
            return {"continuous"}, {"base"}
        if kind == "tempo":
            return {"continuous"}, {"threshold"}
        return set(), set()

    if group == "non-quality":
        if kind == "easy":
            return {"continuous"}, {"base"}
        if kind == "recovery":
            return {"continuous"}, {"recovery"}

    return set(), set()


def classification_for_sheet_code(
    code: object,
) -> tuple[set[str], set[str], set[str]]:
    """Map a sheet ``Trainigstyp`` code to methods, targets, and tags."""
    token = normalize_token(code)
    methods, targets, tags = SHEET_TYPE_CODES.get(token, (set(), set(), set()))
    return set(methods), set(targets), set(tags)
